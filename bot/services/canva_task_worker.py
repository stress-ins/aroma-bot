"""Canva task worker — background export/import via persistent queue.

Runs as a background asyncio task. Uses the same VideoTaskModel table
with task_types 'canva_export' and 'canva_import'. Survives restarts
by recovering interrupted tasks from SQLite on startup.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from bot.services.video_task_store import (
    claim_next_task,
    complete_task,
    fail_task,
    recover_interrupted_tasks,
    update_task_progress,
)

logger = logging.getLogger(__name__)

_CANVA_TASK_TYPES = ("canva_export", "canva_import")

# In-memory status for SSE/polling (fast reads)
# Key: f"{draft_id}:{task_type}"
live_status: dict[str, dict] = {}
_events: dict[str, asyncio.Event] = {}
_worker_task: asyncio.Task | None = None


def _status_key(draft_id: str, task_type: str) -> str:
    return f"{draft_id}:{task_type}"


def notify(draft_id: str, task_type: str) -> None:
    """Wake up SSE listeners."""
    key = _status_key(draft_id, task_type)
    evt = _events.get(key)
    if evt:
        evt.set()


def get_event(draft_id: str, task_type: str) -> asyncio.Event:
    """Get or create an event for SSE streaming."""
    key = _status_key(draft_id, task_type)
    if key not in _events:
        _events[key] = asyncio.Event()
    return _events[key]


async def start_worker() -> None:
    """Start the canva background worker. Call once at app startup."""
    global _worker_task

    try:
        recovered = await recover_interrupted_tasks(task_types=_CANVA_TASK_TYPES)
        if recovered:
            logger.info("canva_worker: recovered %d interrupted tasks", recovered)
    except Exception:
        logger.warning("canva_worker: recovery failed", exc_info=True)

    if _worker_task is None or _worker_task.done():
        _worker_task = asyncio.create_task(_worker_loop())
        logger.info("canva_worker: started")


async def _worker_loop() -> None:
    """Main loop — picks canva tasks one by one."""
    while True:
        try:
            task = await claim_next_task(task_types=_CANVA_TASK_TYPES)
            if not task:
                await asyncio.sleep(3)
                continue

            logger.info(
                "canva_worker: processing %s task %s for draft %s",
                task.task_type, task.task_id, task.draft_id,
            )

            key = _status_key(task.draft_id, task.task_type)
            live_status[key] = {
                "task_id": task.task_id,
                "task_type": task.task_type,
                "status": "running",
                "step": "starting",
            }
            notify(task.draft_id, task.task_type)

            try:
                if task.task_type == "canva_export":
                    result = await _execute_export(task)
                elif task.task_type == "canva_import":
                    result = await _execute_import(task)
                else:
                    raise ValueError(f"Unknown canva task type: {task.task_type}")

                await complete_task(task.task_id, result=result)
                live_status[key] = {
                    "task_id": task.task_id,
                    "task_type": task.task_type,
                    "status": "completed",
                    "step": "done",
                    "result": result,
                }
            except Exception as exc:
                error_msg = str(exc)[:500]
                logger.error("canva_worker: task %s failed: %s", task.task_id, error_msg)
                await fail_task(task.task_id, error=error_msg)
                live_status[key] = {
                    "task_id": task.task_id,
                    "task_type": task.task_type,
                    "status": "failed",
                    "step": "error",
                    "error": error_msg,
                }

            notify(task.draft_id, task.task_type)

        except Exception:
            logger.exception("canva_worker: unexpected error in loop")
            await asyncio.sleep(5)


async def _execute_export(task) -> dict:
    """Upload PPTX to Canva."""
    from bot.services.canva_api import export_to_canva

    config = task.config or {}
    pptx_path = config.get("pptx_path", "")
    title = config.get("title", f"Carousel #{task.draft_id}")

    key = _status_key(task.draft_id, task.task_type)

    live_status[key]["step"] = "uploading"
    notify(task.draft_id, task.task_type)
    await update_task_progress(task.task_id, step="uploading")

    pptx_file = Path(pptx_path)
    if not pptx_file.exists():
        raise FileNotFoundError(f"PPTX file not found: {pptx_path}")

    pptx_bytes = pptx_file.read_bytes()

    result = await export_to_canva(pptx_bytes, title)

    # Clean up temp PPTX
    try:
        pptx_file.unlink(missing_ok=True)
    except Exception:
        logger.debug("canva_worker: failed to clean up temp PPTX %s", pptx_path)

    return result


async def _execute_import(task) -> dict:
    """Export design from Canva, extract images, update draft."""
    from bot.services.canva_api import export_canva_design
    from bot.services.carousel_assets import (
        extract_images_from_pptx,
        save_carousel_slide_asset,
    )
    from bot.services.drafts_store import get_draft, update_draft
    from bot.services.draft_revisions_store import create_revision

    config = task.config or {}
    design_id = config["design_id"]
    draft_id = task.draft_id

    key = _status_key(draft_id, task.task_type)

    # Step 1: export from Canva
    live_status[key]["step"] = "exporting_from_canva"
    notify(draft_id, task.task_type)
    await update_task_progress(task.task_id, step="exporting_from_canva")

    pptx_bytes = await export_canva_design(design_id)
    if not pptx_bytes:
        raise RuntimeError("Canva returned empty export")

    # Step 2: extract images
    live_status[key]["step"] = "extracting_images"
    notify(draft_id, task.task_type)
    await update_task_progress(task.task_id, step="extracting_images")

    loop = asyncio.get_running_loop()
    images = await loop.run_in_executor(None, extract_images_from_pptx, pptx_bytes)
    if not images or all(img is None for img in images):
        raise RuntimeError("No images found in exported PPTX")

    # Step 3: update draft
    live_status[key]["step"] = "updating_draft"
    notify(draft_id, task.task_type)
    await update_task_progress(task.task_id, step="updating_draft")

    draft = await get_draft(draft_id)
    if not draft:
        raise RuntimeError(f"Draft {draft_id} not found")

    img_prompts: list[str] = list(draft.payload.get("img_prompts", []))
    slide_images: list[dict | None] = list(draft.payload.get("slide_images", []))
    slide_versions: list[list] = list(draft.payload.get("slide_image_versions", []))

    while len(slide_images) < len(images):
        slide_images.append(None)
    while len(slide_versions) < len(images):
        slide_versions.append([])

    for i, img_bytes in enumerate(images):
        if img_bytes is None:
            continue
        prompt = img_prompts[i] if i < len(img_prompts) else "canva_import"
        version = save_carousel_slide_asset(draft_id, i, img_bytes, prompt=f"canva_import: {prompt}")
        slide_images[i] = version
        if i < len(slide_versions):
            slide_versions[i].append(version)

    payload = dict(draft.payload)
    payload["slide_images"] = slide_images
    payload["slide_image_versions"] = slide_versions
    payload["images_ready"] = sum(1 for img in slide_images if img)
    payload["canva_design_id"] = design_id

    await update_draft(draft_id, payload=payload, status="approved")
    await create_revision(draft_id, payload, author="canva_import", note=f"Canva design import: {design_id}")

    return {"images_ready": payload["images_ready"], "design_id": design_id}
