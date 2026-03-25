"""Webhook endpoints for external service callbacks (KIE.ai image generation)."""
from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/api/webhooks/kie-callback")
async def kie_callback(request: Request, background_tasks: BackgroundTasks):
    """Receive KIE.ai task completion callback.

    KIE sends the same payload shape as their recordInfo poll endpoint.
    We extract the taskId, look it up in kie_tasks, and process the result.
    """
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)

    # Extract taskId from various response shapes
    inner = data.get("data", {}) if isinstance(data.get("data"), dict) else {}
    task_id = (
        inner.get("taskId")
        or data.get("taskId")
        or inner.get("task_id")
        or data.get("task_id")
        or ""
    )
    if not task_id:
        return JSONResponse({"error": "missing taskId"}, status_code=400)

    from bot.services.kie_task_store import get_task
    task = await get_task(task_id)
    if not task:
        logger.debug("kie_callback: unknown taskId=%s", task_id)
        return JSONResponse({"error": "unknown task"}, status_code=404)

    if task.status != "pending":
        logger.debug("kie_callback: task %s already %s", task_id, task.status)
        return JSONResponse({"status": "already_processed"})

    # Determine success or failure
    state = inner.get("state") or data.get("state", "")

    if state == "success":
        from bot.services.gemini_images import _extract_kie_image_url
        image_url = _extract_kie_image_url(data)
        if not image_url:
            from bot.services.kie_task_store import fail_task
            await fail_task(task_id, "callback success but no image URL")
            logger.warning("kie_callback: task %s success but no image URL", task_id)
            return JSONResponse({"status": "failed", "reason": "no image URL"})

        from bot.services.kie_task_store import complete_task
        completed = await complete_task(task_id, image_url)
        if not completed:
            return JSONResponse({"status": "already_processed"})

        logger.info("kie_callback: task %s completed, url=%s", task_id, image_url[:80])

        if completed.draft_id and completed.content_type:
            background_tasks.add_task(_process_kie_result, completed)

        return JSONResponse({"status": "ok"})

    if state == "fail":
        fail_msg = inner.get("failMsg") or data.get("failMsg", "unknown")
        from bot.services.kie_task_store import fail_task
        await fail_task(task_id, str(fail_msg)[:1000])
        logger.warning("kie_callback: task %s failed: %s", task_id, fail_msg)
        return JSONResponse({"status": "failed"})

    # Not terminal yet (queuing/generating) — ignore, poll will handle
    logger.debug("kie_callback: task %s non-terminal state=%s", task_id, state)
    return JSONResponse({"status": "ignored", "state": state})


async def _process_kie_result(task) -> None:
    """Download image and save to the appropriate draft asset slot."""
    from bot.services.gemini_images import _download_image
    from bot.services.kie_task_store import get_pending_for_draft

    if not task.image_url or not task.draft_id:
        return

    img_bytes = _download_image(task.image_url, f"callback:{task.task_id[:8]}")
    if not img_bytes:
        logger.warning("kie_callback bg: download failed for task %s", task.task_id)
        return

    try:
        if task.content_type == "carousel_slide":
            await _save_carousel_callback(task, img_bytes)
        elif task.content_type == "reels_frame":
            await _save_reels_frame_callback(task, img_bytes)
        elif task.content_type == "reels_v2_frame":
            await _save_reels_v2_frame_callback(task, img_bytes)
        else:
            logger.debug("kie_callback bg: no handler for content_type=%s", task.content_type)
            return
    except Exception:
        logger.exception("kie_callback bg: error processing task %s", task.task_id)
        return

    # Check if all pending tasks for this draft are done
    pending = await get_pending_for_draft(task.draft_id)
    if not pending:
        from bot.services.drafts_store import get_draft, update_draft
        draft = await get_draft(task.draft_id)
        if draft and draft.payload.get("generation_pending"):
            payload = dict(draft.payload)
            payload["generation_pending"] = False
            await update_draft(task.draft_id, payload=payload)
            logger.info("kie_callback bg: all tasks done for draft %s, cleared generation_pending", task.draft_id)


async def _save_carousel_callback(task, img_bytes: bytes) -> None:
    from bot.services.carousel_assets import save_carousel_slide_asset
    from bot.services.drafts_store import get_draft, update_draft

    draft = await get_draft(task.draft_id)
    if not draft or draft.kind != "carousel":
        return

    slide_index = int(task.slot_key)
    img_prompts = draft.payload.get("img_prompts", [])
    from bot.services.carousel_assets import _ensure_slide_versions
    slide_images, slide_versions = _ensure_slide_versions(draft.payload, len(img_prompts))

    layout_style = draft.payload.get("layout_style", "overlay")
    raw_filename = None

    if layout_style == "editorial":
        # Save raw image first, then render editorial on top
        raw_version = save_carousel_slide_asset(task.draft_id, slide_index, img_bytes, prompt=task.prompt)
        raw_filename = raw_version.get("filename")
        slide_text = draft.payload.get("slides", [])[slide_index] if slide_index < len(draft.payload.get("slides", [])) else ""
        accent = draft.payload.get("accent_color", [138, 92, 246])
        accent_rgb = tuple(accent) if isinstance(accent, list) and len(accent) == 3 else (138, 92, 246)
        brand_user = draft.payload.get("brand_username", "")
        is_hook = slide_index == 0
        is_bullet = "\n•" in slide_text or "\n-" in slide_text or "\n*" in slide_text
        try:
            from bot.agents.carousel_editorial import render_editorial_png
            img_bytes = render_editorial_png(
                img_bytes, slide_text,
                slide_index=slide_index,
                accent_color=accent_rgb,
                username=brand_user,
                is_hook=is_hook,
                is_bullet_list=is_bullet,
            )
        except Exception:
            logger.exception("kie_callback bg: editorial render failed for slide %d", slide_index)

    version = save_carousel_slide_asset(task.draft_id, slide_index, img_bytes, prompt=task.prompt)
    if raw_filename:
        version["raw_filename"] = raw_filename
    slide_images[slide_index] = version
    slide_versions[slide_index].append(version)

    payload = dict(draft.payload)
    payload["slide_images"] = slide_images
    payload["slide_image_versions"] = slide_versions
    payload["images_ready"] = sum(1 for img in slide_images if img)
    await update_draft(task.draft_id, payload=payload)
    logger.info("kie_callback bg: saved carousel slide %d for draft %s", slide_index, task.draft_id)


async def _save_reels_frame_callback(task, img_bytes: bytes) -> None:
    from bot.services.reels_assets import save_reels_frame_asset
    from bot.services.drafts_store import get_draft, update_draft

    draft = await get_draft(task.draft_id)
    if not draft or draft.kind != "reels":
        return

    frame_index = int(task.slot_key)
    storyboard = draft.payload.get("storyboard", [])
    if not isinstance(storyboard, list) or frame_index >= len(storyboard):
        return

    asset = save_reels_frame_asset(task.draft_id, frame_index, img_bytes, prompt=task.prompt)
    frame = dict(storyboard[frame_index]) if isinstance(storyboard[frame_index], dict) else {}
    revisions = list(frame.get("asset_revisions", [])) if isinstance(frame.get("asset_revisions"), list) else []
    current_asset = frame.get("current_asset")
    if isinstance(current_asset, dict) and current_asset.get("url"):
        revisions.append(dict(current_asset))
    frame["current_asset"] = asset
    frame["asset_revisions"] = revisions[-5:]
    frame.pop("kie_task_id", None)

    updated_storyboard = list(storyboard)
    updated_storyboard[frame_index] = frame

    payload = dict(draft.payload)
    payload["storyboard"] = updated_storyboard
    payload["images_ready"] = sum(
        1 for f in updated_storyboard
        if isinstance(f, dict) and isinstance(f.get("current_asset"), dict) and f["current_asset"].get("url")
    )
    await update_draft(task.draft_id, payload=payload)
    logger.info("kie_callback bg: saved reels frame %d for draft %s", frame_index, task.draft_id)


async def _save_reels_v2_frame_callback(task, img_bytes: bytes) -> None:
    from bot.services.reels_assets import save_frame_asset
    from bot.services.drafts_store import get_draft, update_draft

    draft = await get_draft(task.draft_id)
    if not draft or draft.kind != "reels_v2":
        return

    frames_raw = draft.payload.get("frames", [])
    if not isinstance(frames_raw, list):
        return

    frame_id = task.slot_key
    asset = save_frame_asset(task.draft_id, frame_id, img_bytes, prompt=task.prompt)

    updated_frames = []
    for item in frames_raw:
        if not isinstance(item, dict):
            updated_frames.append({})
            continue
        frame = dict(item)
        if str(frame.get("id", "")) == frame_id:
            versions = list(frame.get("image_versions", [])) if isinstance(frame.get("image_versions"), list) else []
            old_url = frame.get("image_url", "")
            if old_url:
                versions.append({"url": old_url, "prompt": frame.get("image_prompt", "")})
            frame["image_url"] = asset["url"]
            frame["image_status"] = "ready"
            frame["image_versions"] = versions[-5:]
            frame.pop("kie_task_id", None)
            frame.pop("placement_data", None)
        updated_frames.append(frame)

    payload = dict(draft.payload)
    payload["frames"] = updated_frames
    payload["images_ready"] = sum(
        1 for f in updated_frames
        if isinstance(f, dict) and bool(str(f.get("image_url", "")).strip())
    )
    await update_draft(task.draft_id, payload=payload)
    logger.info("kie_callback bg: saved reels_v2 frame %s for draft %s", frame_id, task.draft_id)
