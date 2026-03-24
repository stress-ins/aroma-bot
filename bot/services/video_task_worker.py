"""Video task worker — processes video tasks from the persistent queue.

Runs as a background asyncio task. Picks up one task at a time,
executes it, and moves to the next. Survives server restarts by
reading pending tasks from the database.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from bot.services.video_task_store import (
    claim_next_task,
    complete_task,
    fail_task,
    recover_interrupted_tasks,
    update_task_progress,
)

logger = logging.getLogger(__name__)

# In-memory status for SSE/polling (fast reads, not persisted)
live_status: dict[str, dict] = {}
_events: dict[str, asyncio.Event] = {}
_worker_task: asyncio.Task | None = None


def notify(draft_id: str) -> None:
    """Wake up any SSE listeners for this draft."""
    evt = _events.get(draft_id)
    if evt:
        evt.set()


def get_event(draft_id: str) -> asyncio.Event:
    """Get or create an event for SSE streaming."""
    if draft_id not in _events:
        _events[draft_id] = asyncio.Event()
    return _events[draft_id]


async def start_worker() -> None:
    """Start the background worker. Call once at app startup."""
    global _worker_task

    try:
        # Ensure table exists (auto-create if missing)
        from db.models import VideoTaskModel, Base
        from sqlalchemy.ext.asyncio import create_async_engine
        from db.session import DATABASE_URL
        _engine = create_async_engine(DATABASE_URL, echo=False)
        async with _engine.begin() as conn:
            await conn.run_sync(
                lambda sync_conn: Base.metadata.create_all(
                    sync_conn, tables=[VideoTaskModel.__table__], checkfirst=True,
                )
            )
        await _engine.dispose()

        # Reset any tasks that were running when server died
        recovered = await recover_interrupted_tasks()
        if recovered:
            logger.info("video_worker: recovered %d interrupted tasks", recovered)
    except Exception:
        logger.warning("video_worker: could not initialize table, will retry", exc_info=True)

    if _worker_task is None or _worker_task.done():
        _worker_task = asyncio.create_task(_worker_loop())
        logger.info("video_worker: started")


async def _worker_loop() -> None:
    """Main worker loop — picks tasks one by one."""
    while True:
        try:
            task = await claim_next_task()
            if not task:
                await asyncio.sleep(3)
                continue

            logger.info(
                "video_worker: processing %s task %s for draft %s",
                task.task_type, task.task_id, task.draft_id,
            )

            live_status[task.draft_id] = {
                "task_id": task.task_id,
                "task_type": task.task_type,
                "status": "running",
                "step": "preparing",
                "progress": 0,
                "video_duration": task.video_duration,
            }
            notify(task.draft_id)

            try:
                if task.task_type == "clean":
                    result = await _execute_clean(task)
                elif task.task_type == "compose":
                    result = await _execute_compose(task)
                else:
                    raise ValueError(f"Unknown task type: {task.task_type}")

                await complete_task(task.task_id, result=result)
                live_status[task.draft_id] = {
                    "task_id": task.task_id,
                    "task_type": task.task_type,
                    "status": "completed",
                    "step": "done",
                    "progress": 100,
                    "result": result,
                }
                notify(task.draft_id)
                logger.info("video_worker: completed %s for draft %s", task.task_type, task.draft_id)

            except Exception as exc:
                error_msg = str(exc)[:500]
                await fail_task(task.task_id, error=error_msg)
                live_status[task.draft_id] = {
                    "task_id": task.task_id,
                    "task_type": task.task_type,
                    "status": "failed",
                    "step": "error",
                    "progress": 0,
                    "error": error_msg,
                }
                notify(task.draft_id)
                logger.error("video_worker: %s failed for draft %s: %s", task.task_type, task.draft_id, exc)

        except Exception:
            logger.exception("video_worker: unexpected error in loop")
            await asyncio.sleep(5)


async def _set_progress(task_id: str, draft_id: str, step: str, progress: int) -> None:
    """Update progress in both DB and live status."""
    await update_task_progress(task_id, step=step, progress=progress)
    if draft_id in live_status:
        live_status[draft_id]["step"] = step
        live_status[draft_id]["progress"] = progress
    notify(draft_id)


async def _execute_clean(task) -> dict:
    """Execute a video cleaning task."""
    from bot.services.reels_video import VIDEO_DIR
    from bot.services.video_processor import ProcessorConfig, process

    draft_id = task.draft_id
    task_id = task.task_id
    config = task.config or {}

    await _set_progress(task_id, draft_id, "preparing", 5)

    from bot.services.drafts_store import get_draft, update_draft
    draft = await get_draft(draft_id)
    if not draft:
        raise ValueError("Draft not found")

    video_filename = str(draft.payload.get("video_filename") or "").strip()
    if not video_filename:
        raise ValueError("No video uploaded")

    video_path = VIDEO_DIR / draft_id / video_filename
    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")

    output_dir = VIDEO_DIR / draft_id

    await _set_progress(task_id, draft_id, "analyzing", 15)

    proc_config = ProcessorConfig(
        input_file=str(video_path),
        output_path=str(output_dir),
        mode="single",
        min_pause_duration=config.get("min_pause_duration", 0.4),
        silence_threshold_db=config.get("silence_threshold_db", -35.0),
        use_whisper=config.get("use_whisper", True),
    )

    use_whisper = config.get("use_whisper", True)
    if use_whisper:
        await _set_progress(task_id, draft_id, "transcribing", 30)
    else:
        await _set_progress(task_id, draft_id, "detecting_silence", 30)

    loop = asyncio.get_running_loop()
    proc_result = await loop.run_in_executor(None, process, proc_config)

    await _set_progress(task_id, draft_id, "assembling", 85)

    # Save results to draft
    payload = dict(draft.payload)
    cleaned_filename = ""
    if proc_result.output_files:
        from pathlib import Path as _Path
        cleaned_filename = _Path(proc_result.output_files[0]).name
    payload["cleaned_video_path"] = cleaned_filename
    payload["cleaning_status"] = "completed"
    payload["cleaning_result"] = {
        "input_duration": round(proc_result.total_input_duration, 1),
        "output_duration": round(proc_result.total_output_duration, 1),
        "removed_duration": round(proc_result.removed_duration, 1),
        "clip_count": proc_result.clip_count,
    }
    payload["keep_intervals"] = [
        [round(s, 2), round(e, 2)] for s, e in proc_result.keep_intervals
    ]
    payload["split_clips"] = []
    payload["split_status"] = ""
    await update_draft(draft_id, payload=payload)

    await _set_progress(task_id, draft_id, "done", 100)
    return payload["cleaning_result"]


async def _execute_compose(task) -> dict:
    """Execute a video composition task."""
    from bot.services.video_pipeline import compose_reel

    draft_id = task.draft_id
    task_id = task.task_id
    config = task.config or {}

    await _set_progress(task_id, draft_id, "preparing", 10)
    await _set_progress(task_id, draft_id, "rendering", 30)

    result = await compose_reel(
        draft_id,
        renderer=config.get("renderer", "ffmpeg"),
        template=config.get("template", "aroma"),
        text_animation=config.get("text_animation", "fade"),
    )

    await _set_progress(task_id, draft_id, "done", 100)
    return result if isinstance(result, dict) else {"video_ready": True}
