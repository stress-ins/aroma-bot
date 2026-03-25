from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from bot.services.carousel_assets import (
    delete_carousel_slide_version,
    extract_images_from_pptx,
    load_carousel_slide_images,
    save_carousel_slide_asset,
    select_carousel_slide_version,
    update_carousel_slide_note,
    update_carousel_slide_text,
)
from bot.handlers.carousel import _build_pptx
from bot.services.drafts_store import DraftRecord, get_draft, update_draft
from bot.services.draft_revisions_store import create_revision
from bot.services.miniapp_presenter import serialize_draft
from ..auth import _require_auth, _resolve_init_data, require_tier
from ..deps import require_draft
from ..generation import complete_carousel_regen_slide, complete_carousel_regenerate_all, set_generation_state
from ..generation._common import get_generation_event, cleanup_generation_event, sse_msg
from ..models import (
    CarouselSlideNotePayload,
    CarouselSlideRegeneratePayload,
    CarouselSlideTextPayload,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _load_brand_avatar(payload: dict) -> bytes | None:
    """Load avatar bytes from brand_avatar_path in draft payload."""
    from pathlib import Path
    avatar_path = payload.get("brand_avatar_path")
    if avatar_path:
        p = Path(avatar_path)
        if p.exists():
            return p.read_bytes()
    return None


@router.get("/api/carousel/{draft_id}")
async def get_carousel(
    background_tasks: BackgroundTasks,
    draft: DraftRecord = Depends(require_draft("carousel")),
):
    payload = draft.payload or {}
    gen_stage = payload.get("generation_stage", "")
    # Auto-trigger image generation for drafts created via Telegram bot
    # that have prompts but no images and no pending generation.
    # Don't re-trigger if generation already failed or is awaiting webhook callback.
    if (
        payload.get("img_prompts")
        and not payload.get("slide_images")
        and not payload.get("generation_pending")
        and gen_stage not in ("error", "awaiting_callback")
    ):
        await set_generation_state(
            draft.draft_id, pending=True, stage="images",
            message="Генерирую картинки для карусели…",
        )
        background_tasks.add_task(
            _auto_populate_carousel, draft.draft_id,
        )
        draft = await get_draft(draft.draft_id) or draft
    return await serialize_draft(draft)


async def _auto_populate_carousel(draft_id: str) -> None:
    """Wrapper for auto-triggered carousel image generation."""
    from bot.services.carousel_assets import populate_carousel_slide_assets

    try:
        status = await populate_carousel_slide_assets(draft_id)
        if status == "awaiting_callback":
            # generation_stage already set to "awaiting_callback" in populate_carousel_slide_assets;
            # keep generation_pending=True so UI shows progress
            await set_generation_state(draft_id, pending=True, stage="awaiting_callback",
                                       message="Картинки генерируются, ожидаем результат…")
        elif status == "error":
            await set_generation_state(
                draft_id, pending=False, stage="error",
                message="Не удалось сгенерировать картинки. Попробуйте ещё раз.",
            )
        else:
            await set_generation_state(draft_id, pending=False)
    except Exception as exc:
        await set_generation_state(
            draft_id,
            pending=False,
            stage="error",
            message="Не удалось сгенерировать картинки. Попробуйте ещё раз.",
            error=str(exc),
        )


REGEN_LIMIT_PER_CARD = 5


@router.post("/api/carousel/{draft_id}/slides/{slide_index}/regenerate", dependencies=[Depends(require_tier("expert"))])
async def regenerate_carousel_slide(
    draft_id: str,
    slide_index: int,
    payload: CarouselSlideRegeneratePayload,
    background_tasks: BackgroundTasks,
    _: None = Depends(_require_auth),
):
    draft = await get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="carousel_not_found")
    regen_count = draft.payload.get("regen_count", 0)
    if regen_count >= REGEN_LIMIT_PER_CARD:
        from bot.handlers.monitor import notify_owner_throttled

        notify_owner_throttled(
            f"⚠️ <b>Regen limit hit</b>\n"
            f"Draft: <code>{draft_id}</code>\n"
            f"Regens: {regen_count}/{REGEN_LIMIT_PER_CARD}",
            dedup_key=f"regen_limit:{draft_id}",
            cooldown=3600,
        )
        raise HTTPException(
            status_code=429,
            detail={"error": "regen_limit", "used": regen_count, "max": REGEN_LIMIT_PER_CARD},
        )
    from bot.services.draft_revisions_store import snapshot_before_regen
    await snapshot_before_regen(draft_id, note=payload.note or f"regen slide {slide_index}")
    await set_generation_state(
        draft_id, pending=True, stage="images",
        message="Перегенерирую картинку для слайда.",
    )
    background_tasks.add_task(complete_carousel_regen_slide, draft_id, slide_index, payload.note)
    refreshed = await get_draft(draft_id)
    if not refreshed:
        raise HTTPException(status_code=404, detail="carousel_not_found")
    return await serialize_draft(refreshed)


@router.post("/api/carousel/{draft_id}/slides/{slide_index}/text")
async def update_carousel_slide_copy(
    draft_id: str,
    slide_index: int,
    payload: CarouselSlideTextPayload,
    _: None = Depends(_require_auth),
):
    updated_payload = await update_carousel_slide_text(draft_id, slide_index, payload.text)
    if updated_payload is None:
        raise HTTPException(status_code=404, detail="carousel_slide_not_found")
    draft = await get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="carousel_not_found")
    return await serialize_draft(draft)


@router.post("/api/carousel/{draft_id}/slides/{slide_index}/note")
async def update_carousel_slide_review_note(
    draft_id: str,
    slide_index: int,
    payload: CarouselSlideNotePayload,
    _: None = Depends(_require_auth),
):
    updated_payload = await update_carousel_slide_note(draft_id, slide_index, payload.note)
    if updated_payload is None:
        raise HTTPException(status_code=404, detail="carousel_slide_not_found")
    draft = await get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="carousel_not_found")
    return await serialize_draft(draft)


@router.post("/api/carousel/{draft_id}/slides/{slide_index}/versions/{version_index}/select")
async def select_carousel_version(
    draft_id: str,
    slide_index: int,
    version_index: int,
    _: None = Depends(_require_auth),
):
    updated_payload = await select_carousel_slide_version(draft_id, slide_index, version_index)
    if updated_payload is None:
        raise HTTPException(status_code=404, detail="carousel_version_not_found")
    draft = await get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="carousel_not_found")
    return await serialize_draft(draft)


@router.delete("/api/carousel/{draft_id}/slides/{slide_index}/versions/{version_index}")
async def delete_carousel_version(
    draft_id: str,
    slide_index: int,
    version_index: int,
    _: None = Depends(_require_auth),
):
    updated_payload = await delete_carousel_slide_version(draft_id, slide_index, version_index)
    if updated_payload is None:
        raise HTTPException(status_code=404, detail="carousel_version_not_found")
    draft = await get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="carousel_not_found")
    return await serialize_draft(draft)


class CarouselLayoutPayload(BaseModel):
    layout_style: str


@router.post("/api/carousel/{draft_id}/layout")
async def change_carousel_layout(
    body: CarouselLayoutPayload,
    draft: DraftRecord = Depends(require_draft("carousel")),
):
    style = body.layout_style if body.layout_style in ("overlay", "editorial") else "overlay"
    payload = dict(draft.payload or {})
    payload["layout_style"] = style
    await update_draft(draft.draft_id, payload=payload)
    refreshed = await get_draft(draft.draft_id)
    if not refreshed:
        raise HTTPException(status_code=404, detail="carousel_not_found")
    return await serialize_draft(refreshed)


@router.post("/api/carousel/{draft_id}/regenerate-all")
async def regenerate_carousel_all(
    background_tasks: BackgroundTasks,
    draft: DraftRecord = Depends(require_draft("carousel")),
):
    await set_generation_state(
        draft.draft_id, pending=True, stage="images", message="Перегенерирую все картинки в карусели."
    )
    background_tasks.add_task(complete_carousel_regenerate_all, draft.draft_id)
    refreshed = await get_draft(draft.draft_id)
    if not refreshed:
        raise HTTPException(status_code=404, detail="carousel_not_found")
    return await serialize_draft(refreshed)


# ── Preview endpoints ──────────────────────────────────────────────────────────

@router.get("/api/carousel/{draft_id}/slides/{slide_index}/preview")
async def carousel_slide_preview(
    draft_id: str,
    slide_index: int,
    _: str = Depends(_resolve_init_data),
):
    """Generate a PNG preview with text overlaid on the slide image."""
    from bot.agents.carousel_preview_agent import generate_slide_preview

    draft = await get_draft(draft_id)
    if not draft or draft.kind != "carousel":
        raise HTTPException(status_code=404, detail="carousel_not_found")

    try:
        png_bytes = await generate_slide_preview(draft_id, slide_index)
    except ValueError as exc:
        logger.warning("slide preview failed: %s", exc)
        raise HTTPException(status_code=400, detail="slide_preview_failed")

    return StreamingResponse(
        iter([png_bytes]),
        media_type="image/png",
        headers={"Content-Disposition": f'inline; filename="preview_{draft_id}_{slide_index}.png"'},
    )


@router.post("/api/carousel/{draft_id}/preview")
async def carousel_preview_all(
    draft_id: str,
    _: None = Depends(_require_auth),
):
    """Generate previews for all slides, save placement data, return draft JSON."""
    from bot.agents.carousel_preview_agent import generate_all_previews

    draft = await get_draft(draft_id)
    if not draft or draft.kind != "carousel":
        raise HTTPException(status_code=404, detail="carousel_not_found")

    await generate_all_previews(draft_id)

    refreshed = await get_draft(draft_id)
    if not refreshed:
        raise HTTPException(status_code=404, detail="carousel_not_found")
    return await serialize_draft(refreshed)


# ── PPTX export/import ─────────────────────────────────────────────────────────

@router.get("/api/carousel/{draft_id}/pptx")
async def carousel_pptx_export(draft_id: str, _: str = Depends(_resolve_init_data)):
    draft = await get_draft(draft_id)
    if not draft or draft.kind != "carousel":
        raise HTTPException(status_code=404, detail="carousel_not_found")
    slides = list(draft.payload.get("slides", []))
    layout_style = draft.payload.get("layout_style", "overlay")

    if layout_style == "editorial":
        from bot.services.carousel_assets import load_carousel_raw_images
        from bot.agents.carousel_export_agent import build_editorial_pptx
        raw_images = load_carousel_raw_images(draft_id, list(draft.payload.get("slide_images", [])))
        accent = draft.payload.get("accent_color", [138, 92, 246])
        accent_rgb = tuple(accent) if isinstance(accent, list) and len(accent) == 3 else (138, 92, 246)
        username = draft.payload.get("brand_username", "")
        _avatar_bytes = _load_brand_avatar(draft.payload)
        pptx_bytes = await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: build_editorial_pptx(
                slides, raw_images or [], accent_rgb, (18, 18, 22), username, _avatar_bytes,
            ),
        )
    else:
        images = load_carousel_slide_images(draft_id, list(draft.payload.get("slide_images", [])))
        placement_data = draft.payload.get("placement_data")
        if placement_data:
            from bot.agents.carousel_export_agent import build_pptx_from_placement
            pptx_bytes = await asyncio.get_running_loop().run_in_executor(
                None, build_pptx_from_placement, slides, images or [], placement_data,
            )
        else:
            pptx_bytes = await asyncio.get_running_loop().run_in_executor(None, _build_pptx, slides, images or None)

    return StreamingResponse(
        iter([pptx_bytes]),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f'attachment; filename="carousel_{draft_id}.pptx"'},
    )


@router.post("/api/carousel/{draft_id}/pptx/import")
async def carousel_pptx_import(
    draft_id: str,
    file: UploadFile = File(...),
    _: None = Depends(_require_auth),
):
    """Import edited PPTX from Canva — extract images, learn text placement corrections."""
    draft = await get_draft(draft_id)
    if not draft or draft.kind != "carousel":
        raise HTTPException(status_code=404, detail="carousel_not_found")

    pptx_bytes = await file.read()
    if not pptx_bytes:
        raise HTTPException(status_code=400, detail="empty_file")

    loop = asyncio.get_running_loop()
    images = await loop.run_in_executor(None, extract_images_from_pptx, pptx_bytes)
    if not images or all(img is None for img in images):
        raise HTTPException(status_code=400, detail="no_images_found_in_pptx")

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

    # Learn from Canva corrections if we had placement_data
    placement_data = payload.get("placement_data")
    if placement_data:
        from bot.agents.carousel_export_agent import (
            extract_text_positions,
            compute_corrections,
            save_corrections,
        )
        proposed = [placement_data.get(str(i)) for i in range(len(images))]
        actual = await loop.run_in_executor(None, extract_text_positions, pptx_bytes)
        corrections = compute_corrections(proposed, actual)
        if corrections:
            await save_corrections(draft_id, corrections)

    await update_draft(draft_id, payload=payload)
    await create_revision(draft_id, payload, author="canva_import", note="PPTX import from Canva")

    refreshed = await get_draft(draft_id)
    if not refreshed:
        raise HTTPException(status_code=404, detail="carousel_not_found")
    return await serialize_draft(refreshed)


# ── Canva integration ─────────────────────────────────────────────────────────


class CanvaImportPayload(BaseModel):
    design_id: str


@router.get("/api/carousel/{draft_id}/canva/status")
async def carousel_canva_status(draft_id: str, _: None = Depends(_require_auth)):
    """Check if Canva is connected (has a valid token)."""
    from bot.services.mentions_store import get_token as _get_token
    token = await _get_token("canva")
    return {"connected": bool(token and token.access_token)}


@router.post("/api/carousel/{draft_id}/canva/export")
async def carousel_canva_export(draft_id: str, _: None = Depends(_require_auth)):
    """Build PPTX and enqueue Canva upload as background task. Returns 202."""
    from pathlib import Path
    from bot.services.video_task_store import enqueue_task, get_active_task_for_draft
    from bot.services.carousel_assets import CAROUSEL_ASSETS_DIR
    from bot.services import canva_task_worker
    from fastapi.responses import JSONResponse

    draft = await get_draft(draft_id)
    if not draft or draft.kind != "carousel":
        raise HTTPException(status_code=404, detail="carousel_not_found")

    existing = await get_active_task_for_draft(draft_id, "canva_export")
    if existing:
        return JSONResponse(status_code=409, content={"detail": "canva_export_already_running", "task_id": existing.task_id})

    # Build PPTX synchronously (fast, ~1-2s)
    slides = list(draft.payload.get("slides", []))
    layout_style = draft.payload.get("layout_style", "overlay")

    if layout_style == "editorial":
        from bot.services.carousel_assets import load_carousel_raw_images
        from bot.agents.carousel_export_agent import build_editorial_pptx
        raw_images = load_carousel_raw_images(draft_id, list(draft.payload.get("slide_images", [])))
        accent = draft.payload.get("accent_color", [138, 92, 246])
        accent_rgb = tuple(accent) if isinstance(accent, list) and len(accent) == 3 else (138, 92, 246)
        username = draft.payload.get("brand_username", "")
        _avatar_bytes = _load_brand_avatar(draft.payload)
        pptx_bytes = await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: build_editorial_pptx(
                slides, raw_images or [], accent_rgb, (18, 18, 22), username, _avatar_bytes,
            ),
        )
    else:
        images = load_carousel_slide_images(draft_id, list(draft.payload.get("slide_images", [])))
        placement_data = draft.payload.get("placement_data")
        if placement_data:
            from bot.agents.carousel_export_agent import build_pptx_from_placement
            pptx_bytes = await asyncio.get_running_loop().run_in_executor(
                None, build_pptx_from_placement, slides, images or [], placement_data,
            )
        else:
            pptx_bytes = await asyncio.get_running_loop().run_in_executor(None, _build_pptx, slides, images or None)

    # Save PPTX to temp file for the worker
    pptx_dir = CAROUSEL_ASSETS_DIR / draft_id
    pptx_dir.mkdir(parents=True, exist_ok=True)
    pptx_path = pptx_dir / "_canva_export.pptx"
    pptx_path.write_bytes(pptx_bytes)

    first_slide = (draft.payload.get("slides") or [None])[0]
    heading = ((first_slide.get("heading", "") if isinstance(first_slide, dict) else "") or draft.payload.get("angle", "") or draft.topic or "").strip()
    title = f"#{draft.draft_id} {heading}" if heading else f"Carousel #{draft.draft_id}"

    task = await enqueue_task(draft_id, "canva_export", {"pptx_path": str(pptx_path), "title": title})

    key = canva_task_worker._status_key(draft_id, "canva_export")
    canva_task_worker.live_status[key] = {
        "task_id": task.task_id, "task_type": "canva_export",
        "status": "pending", "step": "queued",
    }

    return JSONResponse(status_code=202, content={
        "draft_id": draft_id, "task_id": task.task_id, "status": "pending",
    })


@router.get("/api/carousel/{draft_id}/canva/designs")
async def carousel_canva_designs(draft_id: str, _: None = Depends(_require_auth)):
    """List Canva designs for the picker."""
    from bot.services.canva_api import list_canva_designs, CanvaAPIError

    try:
        designs = await list_canva_designs(limit=20)
    except CanvaAPIError as exc:
        logger.error("Canva list designs failed: %s", exc)
        raise HTTPException(status_code=502, detail="canva_list_failed")
    return {"designs": designs}


@router.post("/api/carousel/{draft_id}/canva/import")
async def carousel_canva_import(
    draft_id: str,
    body: CanvaImportPayload,
    _: None = Depends(_require_auth),
):
    """Enqueue Canva design import as background task. Returns 202."""
    from bot.services.video_task_store import enqueue_task, get_active_task_for_draft
    from bot.services import canva_task_worker
    from fastapi.responses import JSONResponse

    draft = await get_draft(draft_id)
    if not draft or draft.kind != "carousel":
        raise HTTPException(status_code=404, detail="carousel_not_found")

    existing = await get_active_task_for_draft(draft_id, "canva_import")
    if existing:
        return JSONResponse(status_code=409, content={"detail": "canva_import_already_running", "task_id": existing.task_id})

    task = await enqueue_task(draft_id, "canva_import", {"design_id": body.design_id})

    key = canva_task_worker._status_key(draft_id, "canva_import")
    canva_task_worker.live_status[key] = {
        "task_id": task.task_id, "task_type": "canva_import",
        "status": "pending", "step": "queued",
    }

    return JSONResponse(status_code=202, content={
        "draft_id": draft_id, "task_id": task.task_id, "status": "pending",
    })


@router.get("/api/carousel/{draft_id}/canva/task-status")
async def carousel_canva_task_status(draft_id: str, _: None = Depends(_require_auth)):
    """Check Canva background task status (polling fallback)."""
    from bot.services import canva_task_worker
    from bot.services.video_task_store import get_active_task_for_draft

    # Check live in-memory status first
    for tt in ("canva_export", "canva_import"):
        key = canva_task_worker._status_key(draft_id, tt)
        live = canva_task_worker.live_status.get(key)
        if live and live.get("status") not in (None, "idle"):
            resp: dict = {"draft_id": draft_id, "task_type": tt, "status": live["status"], "step": live.get("step", "")}
            if live.get("result"):
                resp["result"] = live["result"]
            if live.get("error"):
                resp["error"] = live["error"]
            return resp

    # Fall back to DB
    for tt in ("canva_export", "canva_import"):
        task = await get_active_task_for_draft(draft_id, tt)
        if task:
            resp = {"draft_id": draft_id, "task_type": tt, "status": task.status, "step": task.step or "queued"}
            if task.result:
                resp["result"] = task.result
            if task.error:
                resp["error"] = task.error
            return resp

    return {"draft_id": draft_id, "status": "idle"}


@router.get("/api/carousel/{draft_id}/canva/stream")
async def carousel_canva_stream(draft_id: str, _: str = Depends(_resolve_init_data)):
    """SSE stream for Canva task progress."""
    from bot.services import canva_task_worker

    async def _event_generator():
        # Determine which task type is active
        active_type = None
        for tt in ("canva_export", "canva_import"):
            key = canva_task_worker._status_key(draft_id, tt)
            if canva_task_worker.live_status.get(key):
                active_type = tt
                break

        if not active_type:
            yield sse_msg({"draft_id": draft_id, "status": "idle"})
            return

        key = canva_task_worker._status_key(draft_id, active_type)
        evt = canva_task_worker.get_event(draft_id, active_type)

        for _ in range(180):  # max ~6 min
            live = canva_task_worker.live_status.get(key)
            if not live:
                yield sse_msg({"draft_id": draft_id, "status": "idle"})
                return

            msg: dict = {
                "draft_id": draft_id,
                "task_type": active_type,
                "status": live["status"],
                "step": live.get("step", ""),
            }
            if live.get("result"):
                msg["result"] = live["result"]
            if live.get("error"):
                msg["error"] = live["error"]

            yield sse_msg(msg)

            if live["status"] in ("completed", "failed"):
                return

            evt.clear()
            try:
                await asyncio.wait_for(evt.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                pass

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


# ── SSE stream for real-time carousel generation updates ────────────────

@router.get("/api/carousel/{draft_id}/stream")
async def carousel_generation_stream(draft_id: str, _: str = Depends(_resolve_init_data)):
    """Server-Sent Events stream that pushes carousel generation state."""

    async def _event_generator():
        evt = get_generation_event(draft_id)
        try:
            for _ in range(360):
                draft = await get_draft(draft_id)
                if not draft:
                    yield sse_msg({"error": "not_found"})
                    return
                payload = dict(draft.payload or {})
                slides = payload.get("slides") or []
                slide_images = payload.get("slide_images") or []
                data = {
                    "draft_id": draft_id,
                    "generation_pending": payload.get("generation_pending", False),
                    "generation_stage": payload.get("generation_stage", ""),
                    "generation_message": payload.get("generation_message", ""),
                    "generation_error": payload.get("generation_error"),
                    "slide_count": len(slides),
                    "images_ready": sum(1 for img in slide_images if img),
                    "status": draft.status,
                }
                yield sse_msg(data)
                if not payload.get("generation_pending", False):
                    return
                evt.clear()
                try:
                    await asyncio.wait_for(evt.wait(), timeout=3.0)
                except asyncio.TimeoutError:
                    pass
        finally:
            cleanup_generation_event(draft_id)

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )
