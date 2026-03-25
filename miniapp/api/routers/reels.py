from __future__ import annotations

import logging

import asyncio
import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

from bot.services.miniapp_reels import (
    approve_reels,
    list_reels_drafts,
    record_feedback,
    serialize_reels_draft,
    update_caption,
    update_concept,
    update_frame_field,
    build_reels_export_payload,
    regenerate_reels_storyboard,
    update_reels_frame_fields,
    update_reels_frame_note,
    update_reels_frame_prompt,
    update_reels_scenario,
)
from bot.services.reels_assets import recover_frame_asset, regenerate_reels_frame_asset
from ..auth import _require_auth, _resolve_init_data, require_tier
from ..deps import require_draft
from bot.services.drafts_store import get_draft as _get_draft, update_draft as _update_draft
from ..generation import (
    complete_reels_regenerate_all,
    complete_reels_v2_generate_images,
    complete_reels_v2_generation,
    complete_reels_v2_regen_caption,
    complete_reels_v2_regen_concept_only,
    complete_reels_v2_regen_frame,
    complete_reels_v2_regen_scenario_only,
    set_generation_state,
)
from ..generation._common import get_generation_event, cleanup_generation_event
from ..models import (
    CleanVideoPayload,
    ReelsApprovePayload,
    ReelsFeedbackPayload,
    ReelsFrameFieldsPayload,
    ReelsFrameNotePayload,
    ReelsFramePatchPayload,
    ReelsFramePromptPayload,
    ReelsPublishPayload,
    ReelsRegenFramePayload,
    ReelsRetryPlatformPayload,
    ReelsScenarioPayload,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/api/reels")
async def reels(limit: int = Query(default=30, ge=1, le=100), _: None = Depends(_require_auth)):
    items = await list_reels_drafts(limit=limit)
    return {"items": items, "total": len(items)}


@router.get("/api/reels/{draft_id}")
async def reels_detail(draft_id: str, _: None = Depends(_require_auth)):
    draft = await serialize_reels_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="reels_not_found")
    return draft


@router.patch("/api/reels/{draft_id}/frame")
async def reels_patch_frame(
    draft_id: str,
    payload: ReelsFramePatchPayload,
    _: None = Depends(_require_auth),
):
    frame_id = payload.frame_id.strip()
    if not frame_id:
        raise HTTPException(status_code=400, detail="empty_frame_id")
    draft = await update_frame_field(
        draft_id,
        frame_id,
        overlay_text=payload.overlay_text,
        image_prompt=payload.image_prompt,
    )
    if not draft:
        raise HTTPException(status_code=404, detail="reels_frame_not_found")
    return draft


@router.post("/api/reels/{draft_id}/regen-concept", dependencies=[Depends(require_tier("expert"))])
async def reels_regen_concept(
    draft_id: str,
    background_tasks: BackgroundTasks,
    _: None = Depends(_require_auth),
):
    from bot.services.draft_revisions_store import snapshot_before_regen
    draft = await serialize_reels_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="reels_not_found")
    await snapshot_before_regen(draft_id, note="regen concept")
    topic = str(draft.get("topic", ""))
    payload_data = draft.get("payload", {})
    goal = str(payload_data.get("goal", "trust")) if isinstance(payload_data, dict) else "trust"
    emotion = str(payload_data.get("emotion", "calm")) if isinstance(payload_data, dict) else "calm"
    await set_generation_state(draft_id, pending=True, stage="concept", message="Обновляю концепцию рилса.")
    background_tasks.add_task(complete_reels_v2_regen_concept_only, draft_id, topic, goal, emotion)
    return await serialize_reels_draft(draft_id)


@router.post("/api/reels/{draft_id}/regen-scenario", dependencies=[Depends(require_tier("expert"))])
async def reels_regen_scenario(
    draft_id: str,
    background_tasks: BackgroundTasks,
    _: None = Depends(_require_auth),
):
    from bot.services.draft_revisions_store import snapshot_before_regen
    draft = await serialize_reels_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="reels_not_found")
    await snapshot_before_regen(draft_id, note="regen scenario")
    await set_generation_state(draft_id, pending=True, stage="scenario", message="Перегенерирую сценарий рилса.")
    background_tasks.add_task(complete_reels_v2_regen_scenario_only, draft_id)
    return await serialize_reels_draft(draft_id)


@router.post("/api/reels/{draft_id}/regen-frame-image", dependencies=[Depends(require_tier("expert"))])
async def reels_regen_frame_image(
    draft_id: str,
    payload: ReelsRegenFramePayload,
    background_tasks: BackgroundTasks,
    _: None = Depends(_require_auth),
):
    frame_id = payload.frame_id.strip()
    if not frame_id:
        raise HTTPException(status_code=400, detail="empty_frame_id")
    await set_generation_state(draft_id, pending=True, stage="images", message="Перегенерирую кадр.")
    background_tasks.add_task(complete_reels_v2_regen_frame, draft_id, frame_id, payload.prompt)
    draft = await serialize_reels_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="reels_not_found")
    return draft


@router.post("/api/reels/{draft_id}/generate-images", dependencies=[Depends(require_tier("expert"))])
async def reels_generate_images(
    draft_id: str,
    background_tasks: BackgroundTasks,
    _: None = Depends(_require_auth),
):
    """Generate images for all v2 frames (manual trigger)."""
    await set_generation_state(draft_id, pending=True, stage="images", message="Генерирую изображения для кадров.")
    background_tasks.add_task(complete_reels_v2_generate_images, draft_id)
    draft = await serialize_reels_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="reels_not_found")
    return draft


@router.post("/api/reels/{draft_id}/upgrade-to-full", dependencies=[Depends(require_tier("expert"))])
async def reels_upgrade_to_full(
    draft_id: str,
    background_tasks: BackgroundTasks,
    _: None = Depends(_require_auth),
):
    """Upgrade lightweight reels to full mode: generate frames + images."""
    draft = await _get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="reels_not_found")
    payload = dict(draft.payload or {})
    if not payload.get("lightweight"):
        raise HTTPException(status_code=400, detail="not_lightweight")
    payload["lightweight"] = False
    await _update_draft(draft_id, payload=payload)
    topic = draft.topic
    goal = str(payload.get("goal", "trust"))
    emotion = str(payload.get("emotion", "calm"))
    bc = payload.get("blend_context")
    await set_generation_state(draft_id, pending=True, stage="frames", message="Переход к полной раскадровке.")
    background_tasks.add_task(complete_reels_v2_generation, draft_id, topic, goal, emotion, bc)
    return await serialize_reels_draft(draft_id)


@router.get("/api/reels/{draft_id}/frame-versions/{frame_id}")
async def reels_frame_versions(
    draft_id: str,
    frame_id: str,
    _: None = Depends(_require_auth),
):
    draft_data = await serialize_reels_draft(draft_id)
    if not draft_data:
        raise HTTPException(status_code=404, detail="reels_not_found")
    frames = draft_data.get("frames", [])
    for frame in frames:
        if isinstance(frame, dict) and str(frame.get("id", "")) == frame_id:
            return {"frame_id": frame_id, "versions": frame.get("image_versions", [])}
    raise HTTPException(status_code=404, detail="frame_not_found")


@router.post("/api/reels/{draft_id}/regen-caption", dependencies=[Depends(require_tier("expert"))])
async def reels_regen_caption(
    draft_id: str,
    background_tasks: BackgroundTasks,
    _: None = Depends(_require_auth),
):
    draft = await serialize_reels_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="reels_not_found")
    await set_generation_state(draft_id, pending=True, stage="caption", message="Обновляю описание.")
    background_tasks.add_task(complete_reels_v2_regen_caption, draft_id)
    return draft


@router.patch("/api/reels/{draft_id}/approve")
async def reels_approve(
    draft_id: str,
    payload: ReelsApprovePayload,
    _: None = Depends(_require_auth),
):
    updated = await approve_reels(
        draft_id,
        shooting_deadline_days=payload.shooting_deadline_days,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="reels_not_found")
    return updated


@router.get("/api/reels/{draft_id}/video-status")
async def reels_video_status(
    draft_id: str,
    _: None = Depends(_require_auth),
):
    draft = await serialize_reels_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="reels_not_found")
    frames = draft.get("frames", [])
    ready = sum(1 for f in frames if isinstance(f, dict) and f.get("image_status") == "ready")
    return {
        "draft_id": draft_id,
        "frame_count": draft.get("frame_count", 0),
        "images_ready": ready,
        "approved": draft.get("approved", False),
        "generation_pending": draft.get("generation_pending", False),
        "generation_stage": draft.get("generation_stage", ""),
    }


@router.post("/api/reels/{draft_id}/check-video")
async def reels_check_video(
    draft_id: str,
    _: None = Depends(_require_auth),
):
    from bot.services.reels_video import check_video_tech

    result = await check_video_tech(draft_id)
    if result is None:
        raise HTTPException(status_code=404, detail="reels_not_found")
    return result


@router.post("/api/reels/{draft_id}/publish", dependencies=[Depends(require_tier("expert"))])
async def reels_publish(
    draft_id: str,
    payload: ReelsPublishPayload,
    _: None = Depends(_require_auth),
):
    from bot.services.reels_video import publish_reels_video

    result = await publish_reels_video(
        draft_id,
        platforms=payload.platforms,
        date=payload.date,
        time=payload.time,
        youtube_title=payload.youtube_title,
        youtube_privacy=payload.youtube_privacy,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="reels_not_found")
    return result


@router.post("/api/reels/{draft_id}/retry-platform")
async def reels_retry_platform(
    draft_id: str,
    payload: ReelsRetryPlatformPayload,
    _: None = Depends(_require_auth),
):
    from bot.services.reels_video import publish_reels_video

    result = await publish_reels_video(
        draft_id,
        platforms=[payload.platform],
        date="",
        time="",
    )
    if result is None:
        raise HTTPException(status_code=404, detail="reels_not_found")
    return result


@router.patch("/api/reels/{draft_id}/feedback")
async def reels_feedback(
    draft_id: str,
    payload: ReelsFeedbackPayload,
    _: None = Depends(_require_auth),
):
    updated = await record_feedback(
        draft_id,
        platform=payload.platform,
        rating=payload.rating,
        reaction_types=payload.reaction_types,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="reels_not_found")
    return updated


@router.get("/api/reels/{draft_id}/export")
async def reels_export(draft_id: str, _: None = Depends(_require_auth)):
    payload = await build_reels_export_payload(draft_id)
    if not payload:
        raise HTTPException(status_code=404, detail="reels_not_found")
    return payload


@router.post("/api/reels/{draft_id}/frames/{frame_index}/note")
async def reels_frame_note(
    draft_id: str,
    frame_index: int,
    payload: ReelsFrameNotePayload,
    _: None = Depends(_require_auth),
):
    draft = await update_reels_frame_note(draft_id, frame_index, payload.note)
    if not draft:
        raise HTTPException(status_code=404, detail="reels_frame_not_found")
    return draft


@router.post("/api/reels/{draft_id}/frames/{frame_index}/prompt")
async def reels_frame_prompt(
    draft_id: str,
    frame_index: int,
    payload: ReelsFramePromptPayload,
    _: None = Depends(_require_auth),
):
    prompt = payload.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="empty_prompt")
    draft = await update_reels_frame_prompt(draft_id, frame_index, prompt)
    if not draft:
        raise HTTPException(status_code=404, detail="reels_frame_not_found")
    return draft


@router.post("/api/reels/{draft_id}/frames/{frame_index}/regenerate", dependencies=[Depends(require_tier("expert"))])
async def reels_frame_regenerate(
    draft_id: str,
    frame_index: int,
    _: None = Depends(_require_auth),
):
    regen_payload = await regenerate_reels_frame_asset(draft_id, frame_index)
    if not regen_payload:
        raise HTTPException(status_code=503, detail="reels_frame_regenerate_failed")
    draft = await serialize_reels_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="reels_not_found")
    return draft


@router.post("/api/reels/{draft_id}/frames/{frame_id}/recover")
async def reels_frame_recover(
    draft_id: str,
    frame_id: str,
    _: None = Depends(_require_auth),
):
    """Recover a frame image by re-polling its KIE task ID."""
    result = await recover_frame_asset(draft_id, frame_id)
    if not result:
        raise HTTPException(status_code=404, detail="recovery_failed")
    draft = await serialize_reels_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="reels_not_found")
    return draft


@router.post("/api/reels/{draft_id}/scenario")
async def reels_scenario_update(
    draft_id: str,
    payload: ReelsScenarioPayload,
    _: None = Depends(_require_auth),
):
    if payload.revision_note.strip():
        from bot.services.draft_revisions_store import snapshot_before_regen
        await snapshot_before_regen(draft_id, note=payload.revision_note.strip())
    draft = await update_reels_scenario(
        draft_id, payload.scenario, payload.concept,
        revision_note=payload.revision_note,
    )
    if not draft:
        raise HTTPException(status_code=404, detail="reels_not_found")
    return draft


@router.post("/api/reels/{draft_id}/storyboard/regenerate", dependencies=[Depends(require_tier("expert"))])
async def reels_storyboard_regenerate(
    draft_id: str,
    background_tasks: BackgroundTasks,
    _: None = Depends(_require_auth),
):
    from bot.services.draft_revisions_store import snapshot_before_regen
    await snapshot_before_regen(draft_id, note="regen storyboard")
    draft = await regenerate_reels_storyboard(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="reels_not_found")
    await set_generation_state(draft_id, pending=True, stage="images", message="Генерирую кадры для рилса.")
    background_tasks.add_task(complete_reels_regenerate_all, draft_id)
    draft = await serialize_reels_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="reels_not_found")
    return draft


@router.post("/api/reels/{draft_id}/frames/regenerate-all", dependencies=[Depends(require_tier("expert"))])
async def reels_frames_regenerate_all(
    draft_id: str,
    background_tasks: BackgroundTasks,
    _: None = Depends(_require_auth),
):
    await set_generation_state(
        draft_id, pending=True, stage="images", message="Перегенерирую все кадры рилса."
    )
    background_tasks.add_task(complete_reels_regenerate_all, draft_id)
    serialized = await serialize_reels_draft(draft_id)
    if not serialized:
        raise HTTPException(status_code=404, detail="reels_not_found")
    return serialized


@router.patch("/api/reels/{draft_id}/force-edit")
async def reels_force_edit(
    draft_id: str,
    _: None = Depends(_require_auth),
):
    """Force a stuck-generating reel into draft/edit mode."""
    await set_generation_state(draft_id, pending=False, stage="", message="")
    draft = await serialize_reels_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="reels_not_found")
    return draft


@router.post("/api/reels/{draft_id}/frames/{frame_index}/fields")
async def reels_frame_fields(
    draft_id: str,
    frame_index: int,
    payload: ReelsFrameFieldsPayload,
    _: None = Depends(_require_auth),
):
    draft = await update_reels_frame_fields(
        draft_id,
        frame_index,
        scene=payload.scene,
        angle=payload.angle,
        timecode=payload.timecode,
    )
    if not draft:
        raise HTTPException(status_code=404, detail="reels_frame_not_found")
    return draft


# ---------------------------------------------------------------------------
# Reels preview: AI-powered text placement analysis
# ---------------------------------------------------------------------------

@router.post("/api/reels/{draft_id}/frame/{frame_id}/analyze-placement")
async def reels_analyze_placement(draft_id: str, frame_id: str, _: None = Depends(_require_auth)):
    import asyncio, httpx
    from bot.agents.carousel_preview_agent import analyze_reels_placement
    draft = await serialize_reels_draft(draft_id)
    if not draft: raise HTTPException(status_code=404, detail="reels_not_found")
    frames = draft.get("frames", [])
    frame = None
    for f in frames:
        if isinstance(f, dict) and str(f.get("id", "")) == frame_id: frame = f; break
    if not frame: raise HTTPException(status_code=404, detail="frame_not_found")
    payload_data = draft.get("payload", {})
    if isinstance(payload_data, dict):
        cached = payload_data.get("frame_placement_data", {}).get(frame_id)
        if cached: return cached
    image_url = frame.get("image_url", "")
    if not image_url: raise HTTPException(status_code=400, detail="no_image")
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"http://127.0.0.1:8000{image_url}", timeout=10)
            resp.raise_for_status()
            img_bytes = resp.content
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"image_download_failed: {exc}")
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, analyze_reels_placement, img_bytes)
    from bot.services.drafts_store import get_draft as _get_draft, update_draft as _update_draft
    raw_draft = await _get_draft(draft_id)
    if raw_draft:
        new_payload = dict(raw_draft.payload)
        fpd = new_payload.get("frame_placement_data", {})
        fpd[frame_id] = result
        new_payload["frame_placement_data"] = fpd
        await _update_draft(draft_id, payload=new_payload)
    return result


# ---------------------------------------------------------------------------
# Video pipeline: compose & status
# ---------------------------------------------------------------------------

_compose_logger = logging.getLogger(__name__ + ".compose")

# In-memory compose status tracker (lightweight; not persisted across restarts)
_compose_status: dict[str, dict] = {}


async def _run_compose_task(
    draft_id: str,
    renderer: str = "ffmpeg",
    template: str = "aroma",
    text_animation: str = "fade",
) -> None:
    """Background task that runs the video pipeline and updates status."""
    from bot.services.video_pipeline import compose_reel

    try:
        _compose_status[draft_id] = {"status": "running", "error": None, "result": None}
        result = await compose_reel(
            draft_id,
            renderer=renderer,
            template=template,
            text_animation=text_animation,
        )
        _compose_status[draft_id] = {"status": "completed", "error": None, "result": result}
        _compose_logger.info("Compose completed for draft %s (renderer=%s)", draft_id, renderer)
    except Exception as exc:
        _compose_logger.error("Compose failed for draft %s: %s", draft_id, exc, exc_info=True)
        _compose_status[draft_id] = {"status": "failed", "error": "compose_failed", "result": None}


@router.post("/api/reels/{draft_id}/compose", dependencies=[Depends(require_tier("expert"))])
async def compose_reel_video(
    draft_id: str,
    background_tasks: BackgroundTasks,
    renderer: str = Query(default="ffmpeg", regex="^(ffmpeg|remotion)$"),
    template: str = Query(default="aroma", regex="^(aroma|educational|promo)$"),
    text_animation: str = Query(default="fade", regex="^(fade|slide-up|typewriter|scale-in)$"),
    _: None = Depends(_require_auth),
):
    """Trigger video composition for a reels draft.

    Runs the full pipeline (frames -> video -> voiceover -> music -> final MP4)
    as a background task. Returns 202 Accepted immediately.

    Query params:
        renderer: "ffmpeg" (default) or "remotion"
        template: Remotion template — "aroma", "educational", "promo"
        text_animation: Text animation — "fade", "slide-up", "typewriter", "scale-in"
    """
    draft = await serialize_reels_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="reels_not_found")

    current = _compose_status.get(draft_id)
    if current and current["status"] == "running":
        return JSONResponse(
            status_code=409,
            content={"detail": "compose_already_running", "draft_id": draft_id},
        )

    from bot.services.video_task_store import enqueue_task, estimate_time_seconds, get_active_task_for_draft, pending_count
    from bot.services import video_task_worker

    existing = await get_active_task_for_draft(draft_id, "compose")
    if existing:
        return JSONResponse(
            status_code=409,
            content={"detail": "compose_already_running", "draft_id": draft_id},
        )

    p = draft.get("payload", {}) if isinstance(draft, dict) else {}
    tech = (p.get("tech_check") or {}).get("info") or {}
    video_duration = tech.get("duration_seconds")

    config = {"renderer": renderer, "template": template, "text_animation": text_animation}
    task = await enqueue_task(draft_id, "compose", config, video_duration=video_duration)
    est = estimate_time_seconds("compose", video_duration, config)
    queue_size = await pending_count()

    _compose_status[draft_id] = {"status": "pending", "error": None, "result": None}
    video_task_worker.live_status[draft_id] = {
        "task_id": task.task_id, "task_type": "compose",
        "status": "pending", "step": "queued", "progress": 0,
        "video_duration": video_duration,
    }

    return JSONResponse(
        status_code=202,
        content={
            "draft_id": draft_id,
            "task_id": task.task_id,
            "status": "pending",
            "renderer": renderer,
            "estimated_seconds": est,
            "queue_position": queue_size,
        },
    )


@router.get("/api/reels/{draft_id}/compose-status")
async def compose_reel_status(
    draft_id: str,
    _: None = Depends(_require_auth),
):
    """Check video composition status — checks live status, then DB, then payload."""
    from bot.services import video_task_worker
    from bot.services.video_task_store import get_active_task_for_draft, estimate_time_seconds

    # 1. Live status
    live = video_task_worker.live_status.get(draft_id)
    if live and live.get("task_type") == "compose":
        resp: dict = {
            "draft_id": draft_id, "status": live["status"],
            "step": live.get("step", ""), "progress": live.get("progress", 0),
        }
        if live.get("error"):
            resp["error"] = live["error"]
        if live.get("result"):
            resp["result"] = live["result"]
        if live.get("video_duration"):
            resp["estimated_seconds"] = estimate_time_seconds("compose", live["video_duration"])
        return resp

    # 2. Task queue
    task = await get_active_task_for_draft(draft_id, "compose")
    if task:
        return {
            "draft_id": draft_id, "status": task.status,
            "step": task.step or "queued", "progress": task.progress,
            "estimated_seconds": estimate_time_seconds("compose", task.video_duration) if task.video_duration else None,
        }

    # 3. Legacy in-memory
    status = _compose_status.get(draft_id)
    if status:
        resp = {"draft_id": draft_id, "status": status["status"]}
        if status.get("error"):
            resp["error"] = status["error"]
        if status.get("result"):
            resp["result"] = status["result"]
        return resp

    # 4. Draft payload
    draft = await serialize_reels_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="reels_not_found")
    payload = draft.get("payload", {})
    if isinstance(payload, dict) and payload.get("video_ready"):
        return {
            "draft_id": draft_id, "status": "completed",
            "video_path": payload.get("video_path"),
            "video_url": payload.get("video_url"),
        }
    return {"draft_id": draft_id, "status": "not_started"}


# ── Remotion preview frames ──────────────────────────────────────────────────


@router.get("/api/reels/{draft_id}/preview-frames")
async def reels_preview_frames(
    draft_id: str,
    count: int = Query(default=4, ge=1, le=8),
    template: str = Query(default="aroma", regex="^(aroma|educational|promo)$"),
    text_animation: str = Query(default="fade", regex="^(fade|slide-up|typewriter|scale-in)$"),
    _: None = Depends(_require_auth),
):
    """Render key frame stills via Remotion for preview filmstrip."""
    from bot.services.remotion_renderer import render_still
    from bot.services.reels_assets import ASSETS_DIR
    from bot.services.video_pipeline import _find_frame_images, _extract_overlay_texts

    draft = await _get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="reels_not_found")

    payload = dict(draft.payload or {})
    frame_paths = _find_frame_images(draft_id, payload)
    if not frame_paths:
        raise HTTPException(status_code=400, detail="no_frame_images")

    overlay_texts = _extract_overlay_texts(payload)
    output_dir = ASSETS_DIR / draft_id / "preview_frames"

    try:
        stills = await render_still(
            frame_paths=frame_paths,
            overlay_texts=overlay_texts if any(overlay_texts) else None,
            output_dir=output_dir,
            template=template,
            text_animation=text_animation,
            count=count,
        )
    except RuntimeError as exc:
        logger.error("Preview frames generation failed: %s", exc)
        raise HTTPException(status_code=503, detail="preview_generation_failed")

    urls = [
        f"/generated/reels_assets/{draft_id}/preview_frames/{p.name}"
        for p in stills
    ]
    return {"draft_id": draft_id, "preview_urls": urls, "count": len(urls)}


# ── Notification subscription ────────────────────────────────────────────────


@router.post("/api/reels/notify-when-ready")
async def reels_notify_when_ready(
    telegram_id: int = Depends(_require_auth),
):
    """Subscribe current user to Telegram notification when video task completes."""
    from bot.services.video_task_worker import subscribe_notification

    # Subscribe to all active tasks
    from bot.services.video_task_store import AsyncSessionLocal
    from db.models import VideoTaskModel
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(VideoTaskModel.draft_id)
            .where(VideoTaskModel.status.in_(["pending", "running"]))
        )
        draft_ids = [r[0] for r in result.all()]

    if not draft_ids:
        raise HTTPException(status_code=404, detail="no_active_tasks")

    for did in draft_ids:
        subscribe_notification(did, int(telegram_id))

    return {"subscribed": len(draft_ids)}


# ── Auto-montage ────────────────────────────────────────────────────────────


@router.post("/api/reels/{draft_id}/montage")
async def start_montage(
    draft_id: str,
    template: str = "expert",
    transitions_enabled: bool = True,
    transition_type: str = "fade",
    subtitles_enabled: bool = True,
    subtitle_source: str = "auto",
    subtitle_style: str = "bottom_bar",
    music_enabled: bool = False,
    music_track: str = "",
    broll_enabled: bool = False,
    beat_sync_enabled: bool = False,
    color_grade_enabled: bool = False,
    _: None = Depends(_require_auth),
):
    """Queue auto-montage task for a reels draft."""
    from bot.services.video_task_store import enqueue_task, estimate_time_seconds, pending_count
    from bot.services import video_task_worker

    draft = await serialize_reels_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="reels_not_found")

    p = draft.get("payload", {}) if isinstance(draft, dict) else {}
    video_filename = p.get("cleaned_video_path") or p.get("video_filename") or ""
    if not video_filename:
        raise HTTPException(status_code=400, detail="no_video")

    tech = (p.get("tech_check") or {}).get("info") or {}
    video_duration = tech.get("duration_seconds")

    # Collect B-roll frames from reels storyboard
    broll_frames = []
    if broll_enabled:
        from bot.services.reels_video import VIDEO_DIR
        storyboard = p.get("storyboard") or []
        for frame in storyboard:
            if isinstance(frame, dict) and frame.get("image_url"):
                img_path = frame["image_url"]
                if img_path.startswith("/"):
                    # Convert URL to file path
                    img_path = str(Path("/opt/aroma") / img_path.lstrip("/"))
                broll_frames.append(img_path)

    config = {
        "template": template,
        "transitions_enabled": transitions_enabled,
        "transition_type": transition_type,
        "subtitles_enabled": subtitles_enabled,
        "subtitle_source": subtitle_source,
        "subtitle_style": subtitle_style,
        "music_enabled": music_enabled,
        "music_track": music_track,
        "broll_enabled": broll_enabled,
        "broll_frames": broll_frames[:3],
        "beat_sync_enabled": beat_sync_enabled,
        "color_grade_enabled": color_grade_enabled,
        "color_grade_vf": p.get("grade_vf_string", ""),
    }

    task = await enqueue_task(draft_id, "montage", config, video_duration=video_duration)
    est = estimate_time_seconds("compose", video_duration)
    queue_size = await pending_count()

    return JSONResponse(
        status_code=202,
        content={
            "draft_id": draft_id,
            "task_id": task.task_id,
            "status": "pending",
            "template": template,
            "estimated_seconds": est,
            "queue_position": queue_size,
        },
    )


# ── Video color grading ──────────────────────────────────────────────────────


@router.post("/api/reels/{draft_id}/grade-preview")
async def grade_preview_frame(
    draft_id: str,
    brightness: float = 0.0,
    contrast: float = 1.0,
    saturation: float = 1.0,
    gamma: float = 1.0,
    _: None = Depends(_require_auth),
):
    """Extract a mid-frame, apply color correction, return preview image URL."""
    from bot.services.reels_video import VIDEO_DIR
    from pathlib import Path
    import subprocess

    draft = await serialize_reels_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="reels_not_found")

    p = draft.get("payload", {}) if isinstance(draft, dict) else {}
    video_filename = p.get("cleaned_video_path") or p.get("video_filename") or ""
    if not video_filename:
        raise HTTPException(status_code=400, detail="no_video")

    video_path = VIDEO_DIR / draft_id / video_filename
    if not video_path.exists():
        raise HTTPException(status_code=400, detail="video_file_missing")

    # Get duration for mid-frame
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
        capture_output=True, text=True, timeout=15,
    )
    duration = float(probe.stdout.strip()) if probe.returncode == 0 else 10.0
    mid_ts = duration * 0.5

    preview_dir = VIDEO_DIR / draft_id / "grade_preview"
    preview_dir.mkdir(parents=True, exist_ok=True)

    # Build filter string from sliders
    vf_parts = []
    eq_parts = []
    if brightness != 0.0:
        eq_parts.append(f"brightness={brightness}")
    if contrast != 1.0:
        eq_parts.append(f"contrast={contrast}")
    if saturation != 1.0:
        eq_parts.append(f"saturation={saturation}")
    if gamma != 1.0:
        eq_parts.append(f"gamma={gamma}")

    vf = f"eq={'='.join(eq_parts) if len(eq_parts) == 1 else ':'.join(eq_parts)}" if eq_parts else ""

    # Extract original frame
    orig_path = str(preview_dir / "original.jpg")
    subprocess.run(
        ["ffmpeg", "-ss", str(mid_ts), "-i", str(video_path),
         "-vframes", "1", "-q:v", "2", "-y", orig_path],
        capture_output=True, timeout=15,
    )

    # Extract corrected frame
    corrected_path = str(preview_dir / "corrected.jpg")
    cmd = ["ffmpeg", "-ss", str(mid_ts), "-i", str(video_path), "-vframes", "1", "-q:v", "2"]
    if vf:
        cmd += ["-vf", vf]
    cmd += ["-y", corrected_path]
    subprocess.run(cmd, capture_output=True, timeout=15)

    return {
        "original_url": f"/generated/reels_video/{draft_id}/grade_preview/original.jpg",
        "corrected_url": f"/generated/reels_video/{draft_id}/grade_preview/corrected.jpg",
        "vf_string": vf,
    }


@router.post("/api/reels/{draft_id}/grade-analyze")
async def grade_analyze(
    draft_id: str,
    style: str = "warm_natural",
    _: None = Depends(_require_auth),
):
    """Analyze video frame stats via ffprobe and recommend corrections for given style."""
    import subprocess
    from bot.services.reels_video import VIDEO_DIR

    draft = await serialize_reels_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="reels_not_found")

    p = draft.get("payload", {}) if isinstance(draft, dict) else {}
    video_filename = p.get("cleaned_video_path") or p.get("video_filename") or ""
    if not video_filename:
        raise HTTPException(status_code=400, detail="no_video")

    video_path = VIDEO_DIR / draft_id / video_filename
    if not video_path.exists():
        raise HTTPException(status_code=400, detail="video_file_missing")

    # Get duration for mid-frame
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
        capture_output=True, text=True, timeout=15,
    )
    duration = float(probe.stdout.strip()) if probe.returncode == 0 else 10.0

    # Analyze 3 frames: 20%, 50%, 80%
    stats = []
    for pct in (0.2, 0.5, 0.8):
        ts = duration * pct
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-read_intervals", f"%{ts:.1f}%+#1",
             "-show_entries", "frame=pkt_pts_time",
             "-show_entries", "frame_tags=lavfi.signalstats.YAVG,lavfi.signalstats.YMIN,lavfi.signalstats.YMAX,lavfi.signalstats.SATAVG",
             "-f", "lavfi", "-i", f"movie='{str(video_path)}',signalstats",
             "-of", "csv=p=0", "-frames:v", "1"],
            capture_output=True, text=True, timeout=30,
        )
        # Fallback: use simpler brightness measurement
        bright_result = subprocess.run(
            ["ffmpeg", "-ss", str(ts), "-i", str(video_path),
             "-vframes", "1", "-vf", "scale=64:64,format=gray",
             "-f", "rawvideo", "-pix_fmt", "gray", "pipe:1"],
            capture_output=True, timeout=15,
        )
        avg_brightness = 128.0
        if bright_result.returncode == 0 and bright_result.stdout:
            pixels = bright_result.stdout
            avg_brightness = sum(pixels) / len(pixels) if pixels else 128.0

        stats.append({
            "timestamp": round(ts, 1),
            "brightness": round(avg_brightness / 255.0, 3),
        })

    avg_bright = sum(s["brightness"] for s in stats) / len(stats) if stats else 0.5

    # Style presets — corrections based on measured brightness
    STYLE_PRESETS = {
        "warm_natural": {
            "brightness": round(max(-0.1, 0.55 - avg_bright) * 0.5, 2),
            "contrast": 1.1,
            "saturation": 1.15,
            "gamma": 1.05 if avg_bright < 0.45 else 0.95,
            "description": "Тёплый натуральный — мягкий свет, лёгкая насыщенность",
        },
        "luxury_dark": {
            "brightness": round(max(-0.15, 0.40 - avg_bright) * 0.6, 2),
            "contrast": 1.35,
            "saturation": 0.85,
            "gamma": 0.85,
            "description": "Тёмный люкс — глубокие тени, приглушённые цвета",
        },
        "fresh_light": {
            "brightness": round(max(0, 0.65 - avg_bright) * 0.5, 2),
            "contrast": 0.95,
            "saturation": 1.1,
            "gamma": 1.15,
            "description": "Свежий светлый — чистота, воздушность",
        },
        "moody_cinematic": {
            "brightness": round(max(-0.12, 0.42 - avg_bright) * 0.5, 2),
            "contrast": 1.4,
            "saturation": 0.9,
            "gamma": 0.8,
            "description": "Кинематографичный — контраст, тёмные тона",
        },
    }

    preset = STYLE_PRESETS.get(style, STYLE_PRESETS["warm_natural"])

    return {
        "style": style,
        "description": preset["description"],
        "measured_brightness": round(avg_bright, 3),
        "recommendations": {
            "brightness": preset["brightness"],
            "contrast": preset["contrast"],
            "saturation": preset["saturation"],
            "gamma": preset["gamma"],
        },
        "frame_stats": stats,
    }


@router.post("/api/reels/{draft_id}/grade-analyze-all")
async def grade_analyze_all(
    draft_id: str,
    _: None = Depends(_require_auth),
):
    """Analyze video and return recommendations + preview thumbnails for ALL styles."""
    import subprocess
    from bot.services.reels_video import VIDEO_DIR

    draft = await serialize_reels_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="reels_not_found")

    p = draft.get("payload", {}) if isinstance(draft, dict) else {}
    video_filename = p.get("cleaned_video_path") or p.get("video_filename") or ""
    if not video_filename:
        raise HTTPException(status_code=400, detail="no_video")

    video_path = VIDEO_DIR / draft_id / video_filename
    if not video_path.exists():
        raise HTTPException(status_code=400, detail="video_file_missing")

    # Get duration
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
        capture_output=True, text=True, timeout=15,
    )
    duration = float(probe.stdout.strip()) if probe.returncode == 0 else 10.0
    mid_ts = duration * 0.5

    # Measure brightness from 3 frames
    stats = []
    for pct in (0.2, 0.5, 0.8):
        ts = duration * pct
        bright_result = subprocess.run(
            ["ffmpeg", "-ss", str(ts), "-i", str(video_path),
             "-vframes", "1", "-vf", "scale=64:64,format=gray",
             "-f", "rawvideo", "-pix_fmt", "gray", "pipe:1"],
            capture_output=True, timeout=15,
        )
        avg_brightness = 128.0
        if bright_result.returncode == 0 and bright_result.stdout:
            pixels = bright_result.stdout
            avg_brightness = sum(pixels) / len(pixels) if pixels else 128.0
        stats.append({"timestamp": round(ts, 1), "brightness": round(avg_brightness / 255.0, 3)})

    avg_bright = sum(s["brightness"] for s in stats) / len(stats) if stats else 0.5

    # Style presets
    STYLE_PRESETS = {
        "warm_natural": {
            "brightness": round(max(-0.1, 0.55 - avg_bright) * 0.5, 2),
            "contrast": 1.1,
            "saturation": 1.15,
            "gamma": 1.05 if avg_bright < 0.45 else 0.95,
            "description": "Тёплый натуральный",
            "subtitle": "мягкий свет, лёгкая насыщенность",
        },
        "luxury_dark": {
            "brightness": round(max(-0.15, 0.40 - avg_bright) * 0.6, 2),
            "contrast": 1.35,
            "saturation": 0.85,
            "gamma": 0.85,
            "description": "Тёмный люкс",
            "subtitle": "глубокие тени, приглушённые цвета",
        },
        "fresh_light": {
            "brightness": round(max(0, 0.65 - avg_bright) * 0.5, 2),
            "contrast": 0.95,
            "saturation": 1.1,
            "gamma": 1.15,
            "description": "Свежий светлый",
            "subtitle": "чистота, воздушность",
        },
        "moody_cinematic": {
            "brightness": round(max(-0.12, 0.42 - avg_bright) * 0.5, 2),
            "contrast": 1.4,
            "saturation": 0.9,
            "gamma": 0.8,
            "description": "Кинематографичный",
            "subtitle": "контраст, тёмные тона",
        },
    }

    preview_dir = VIDEO_DIR / draft_id / "grade_preview"
    preview_dir.mkdir(parents=True, exist_ok=True)

    # Extract original frame once
    orig_path = str(preview_dir / "original.jpg")
    subprocess.run(
        ["ffmpeg", "-ss", str(mid_ts), "-i", str(video_path),
         "-vframes", "1", "-q:v", "2", "-y", orig_path],
        capture_output=True, timeout=15,
    )

    # Generate preview for each style
    profiles = []
    for style_key, preset in STYLE_PRESETS.items():
        eq_parts = []
        if preset["brightness"] != 0.0:
            eq_parts.append(f"brightness={preset['brightness']}")
        if preset["contrast"] != 1.0:
            eq_parts.append(f"contrast={preset['contrast']}")
        if preset["saturation"] != 1.0:
            eq_parts.append(f"saturation={preset['saturation']}")
        if preset["gamma"] != 1.0:
            eq_parts.append(f"gamma={preset['gamma']}")

        vf = f"eq={':'.join(eq_parts)}" if eq_parts else ""
        thumb_name = f"profile_{style_key}.jpg"
        thumb_path = str(preview_dir / thumb_name)

        cmd = ["ffmpeg", "-ss", str(mid_ts), "-i", str(video_path),
               "-vframes", "1", "-q:v", "3", "-vf", f"scale=320:-1{(',' + vf) if vf else ''}",
               "-y", thumb_path]
        subprocess.run(cmd, capture_output=True, timeout=15)

        profiles.append({
            "style": style_key,
            "name": preset["description"],
            "subtitle": preset["subtitle"],
            "recommendations": {
                "brightness": preset["brightness"],
                "contrast": preset["contrast"],
                "saturation": preset["saturation"],
                "gamma": preset["gamma"],
            },
            "preview_url": f"/generated/reels_video/{draft_id}/grade_preview/{thumb_name}",
        })

    return {
        "profiles": profiles,
        "original_url": f"/generated/reels_video/{draft_id}/grade_preview/original.jpg",
        "measured_brightness": round(avg_bright, 3),
        "frame_stats": stats,
    }


@router.post("/api/reels/{draft_id}/grade-apply")
async def grade_apply(
    draft_id: str,
    brightness: float = 0.0,
    contrast: float = 1.0,
    saturation: float = 1.0,
    gamma: float = 1.0,
    custom_vf: str = "",
    _: None = Depends(_require_auth),
):
    """Apply color correction to video and save as graded version."""
    from bot.services.video_task_store import enqueue_task, pending_count, estimate_time_seconds
    from bot.services import video_task_worker

    draft = await serialize_reels_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="reels_not_found")

    p = draft.get("payload", {}) if isinstance(draft, dict) else {}
    video_filename = p.get("cleaned_video_path") or p.get("video_filename") or ""
    if not video_filename:
        raise HTTPException(status_code=400, detail="no_video")

    # Build vf_string
    if custom_vf:
        vf_string = custom_vf
    else:
        eq_parts = []
        if brightness != 0.0:
            eq_parts.append(f"brightness={brightness}")
        if contrast != 1.0:
            eq_parts.append(f"contrast={contrast}")
        if saturation != 1.0:
            eq_parts.append(f"saturation={saturation}")
        if gamma != 1.0:
            eq_parts.append(f"gamma={gamma}")
        vf_string = f"eq={':'.join(eq_parts)}" if eq_parts else ""

    if not vf_string:
        raise HTTPException(status_code=400, detail="no_corrections")

    # Get duration for estimate
    tech = (p.get("tech_check") or {}).get("info") or {}
    video_duration = tech.get("duration_seconds")

    config = {
        "vf_string": vf_string,
        "video_filename": video_filename,
    }
    task = await enqueue_task(
        draft_id, "grade", config, video_duration=video_duration,
    )
    est = estimate_time_seconds("compose", video_duration)
    queue_size = await pending_count()

    return JSONResponse(
        status_code=202,
        content={
            "draft_id": draft_id,
            "task_id": task.task_id,
            "status": "pending",
            "vf_string": vf_string,
            "estimated_seconds": est,
            "queue_position": queue_size,
        },
    )


# ── Video upload & cleaning ──────────────────────────────────────────────────


@router.post("/api/reels/{draft_id}/upload-video")
async def upload_reels_video(
    draft_id: str,
    file: UploadFile,
    _: None = Depends(_require_auth),
):
    """Upload a raw video file for a reels draft."""
    from bot.services.reels_video import save_uploaded_video

    draft = await serialize_reels_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="reels_not_found")

    video_bytes = await file.read()
    if not video_bytes:
        raise HTTPException(status_code=400, detail="empty_file")

    result = await save_uploaded_video(draft_id, video_bytes, file.filename or "video.mp4")
    return result


_clean_status: dict[str, dict] = {}
_clean_events: dict[str, asyncio.Event] = {}
_clean_logger = logging.getLogger(__name__ + ".clean_video")


def _notify_clean_event(draft_id: str) -> None:
    evt = _clean_events.get(draft_id)
    if evt:
        evt.set()


async def _run_clean_video_task(
    draft_id: str,
    min_pause_duration: float,
    silence_threshold_db: float,
    use_whisper: bool = True,
) -> None:
    """Background task: run video_processor on uploaded video."""
    import asyncio

    from bot.services.reels_video import VIDEO_DIR

    def _set_step(step: str, progress: int = 0):
        _clean_status[draft_id] = {
            "status": "running", "error": None, "result": None,
            "step": step, "progress": progress,
        }
        _notify_clean_event(draft_id)

    try:
        _set_step("preparing", 0)

        draft = await _get_draft(draft_id)
        if not draft:
            raise ValueError("Draft not found")

        video_filename = str(draft.payload.get("video_filename") or "").strip()
        if not video_filename:
            raise ValueError("No video uploaded")

        video_path = VIDEO_DIR / draft_id / video_filename
        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")

        output_dir = VIDEO_DIR / draft_id
        from bot.services.video_processor import ProcessorConfig, process

        _set_step("analyzing", 15)

        config = ProcessorConfig(
            input_file=str(video_path),
            output_path=str(output_dir),
            mode="single",
            min_pause_duration=min_pause_duration,
            silence_threshold_db=silence_threshold_db,
            use_whisper=use_whisper,
        )

        if use_whisper:
            _set_step("transcribing", 30)
        else:
            _set_step("detecting_silence", 30)

        loop = asyncio.get_running_loop()
        proc_result = await loop.run_in_executor(None, process, config)

        _set_step("assembling", 85)

        payload = dict(draft.payload)
        cleaned_filename = ""
        if proc_result.output_files:
            from pathlib import Path

            cleaned_filename = Path(proc_result.output_files[0]).name
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
        await _update_draft(draft_id, payload=payload)

        _clean_status[draft_id] = {
            "status": "completed",
            "error": None,
            "result": payload["cleaning_result"],
        }
        _notify_clean_event(draft_id)
        _clean_logger.info("Video cleaning completed for draft %s", draft_id)

    except Exception as exc:
        _clean_logger.error(
            "Video cleaning failed for draft %s: %s", draft_id, exc, exc_info=True,
        )
        _clean_status[draft_id] = {"status": "failed", "error": "cleaning_failed", "result": None}
        _notify_clean_event(draft_id)
        try:
            draft = await _get_draft(draft_id)
            if draft:
                payload = dict(draft.payload)
                payload["cleaning_status"] = "failed"
                payload["cleaning_error"] = "cleaning_failed"
                await _update_draft(draft_id, payload=payload)
        except Exception:
            pass


@router.post("/api/reels/{draft_id}/clean-video")
async def clean_reels_video(
    draft_id: str,
    payload: CleanVideoPayload,
    _: None = Depends(_require_auth),
):
    """Start video cleaning (silence removal) via persistent task queue."""
    from bot.services.video_task_store import enqueue_task, estimate_time_seconds, get_active_task_for_draft, pending_count
    from bot.services import video_task_worker

    draft = await serialize_reels_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="reels_not_found")

    existing = await get_active_task_for_draft(draft_id, "clean")
    if existing:
        return JSONResponse(
            status_code=409,
            content={"detail": "clean_already_running", "draft_id": draft_id},
        )

    # Get video duration for time estimation
    p = draft.get("payload", {}) if isinstance(draft, dict) else {}
    tech = p.get("tech_check") or {}
    info = tech.get("info") or {}
    video_duration = info.get("duration_seconds")

    config = {
        "min_pause_duration": payload.min_pause_duration,
        "silence_threshold_db": payload.silence_threshold_db,
        "use_whisper": payload.use_whisper,
    }
    task = await enqueue_task(
        draft_id, "clean", config, video_duration=video_duration,
    )
    est = estimate_time_seconds("clean", video_duration, config)
    queue_size = await pending_count()

    # Update in-memory status for SSE
    _clean_status[draft_id] = {"status": "pending", "error": None, "result": None, "step": "queued", "progress": 0}
    video_task_worker.live_status[draft_id] = {
        "task_id": task.task_id, "task_type": "clean",
        "status": "pending", "step": "queued", "progress": 0,
        "video_duration": video_duration,
    }

    return JSONResponse(
        status_code=202,
        content={
            "draft_id": draft_id,
            "task_id": task.task_id,
            "status": "pending",
            "estimated_seconds": est,
            "queue_position": queue_size,
        },
    )


@router.get("/api/reels/{draft_id}/clean-video-status")
async def clean_video_status(
    draft_id: str,
    _: None = Depends(_require_auth),
):
    """Check video cleaning status — checks live status, then DB task, then draft payload."""
    from bot.services import video_task_worker
    from bot.services.video_task_store import get_active_task_for_draft, estimate_time_seconds, get_queue_position

    # 1. Check live in-memory status (fastest)
    live = video_task_worker.live_status.get(draft_id)
    if live and live.get("task_type") == "clean":
        resp: dict = {
            "draft_id": draft_id,
            "status": live["status"],
            "step": live.get("step", ""),
            "progress": live.get("progress", 0),
        }
        if live.get("error"):
            resp["error"] = live["error"]
        if live.get("result"):
            resp["result"] = live["result"]
        if live.get("video_duration"):
            resp["estimated_seconds"] = estimate_time_seconds(
                "clean", live["video_duration"],
            )
        return resp

    # 2. Check persistent task queue
    task = await get_active_task_for_draft(draft_id, "clean")
    if task:
        resp = {
            "draft_id": draft_id,
            "status": task.status,
            "step": task.step or "queued",
            "progress": task.progress,
        }
        if task.video_duration:
            resp["estimated_seconds"] = estimate_time_seconds(
                "clean", task.video_duration, task.config,
            )
        pos = await get_queue_position(task.task_id)
        if pos > 0:
            resp["queue_position"] = pos
        return resp

    # 3. Fallback: check in-memory dict (legacy)
    status = _clean_status.get(draft_id)
    if status:
        resp = {"draft_id": draft_id, "status": status["status"]}
        for key in ("error", "result", "step", "progress"):
            if status.get(key):
                resp[key] = status[key]
        return resp

    # 4. Check draft payload
    draft = await serialize_reels_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="reels_not_found")
    p = draft.get("payload", {})
    if isinstance(p, dict) and p.get("cleaning_status") == "completed":
        return {
            "draft_id": draft_id,
            "status": "completed",
            "result": p.get("cleaning_result"),
        }
    return {"draft_id": draft_id, "status": "not_started"}


# ── SSE stream for real-time generation updates ─────────────────────────

@router.get("/api/reels/{draft_id}/stream")
async def reels_generation_stream(draft_id: str, _: str = Depends(_resolve_init_data)):
    """Server-Sent Events stream that pushes generation state changes."""

    async def _event_generator():
        evt = get_generation_event(draft_id)
        try:
            for _ in range(360):  # max ~6 minutes
                draft = await _get_draft(draft_id)
                if not draft:
                    yield _sse_msg({"error": "not_found"})
                    return
                serialized = await serialize_reels_draft(draft.draft_id) or {}
                payload = draft.payload or {}
                data = {
                    "draft_id": draft_id,
                    "generation_pending": payload.get("generation_pending", False),
                    "generation_stage": payload.get("generation_stage", ""),
                    "generation_message": payload.get("generation_message", ""),
                    "generation_error": payload.get("generation_error"),
                    "status": serialized.get("status", draft.status),
                    "frames": serialized.get("frames", []),
                    "images_ready": serialized.get("images_ready", 0),
                    "frame_count": serialized.get("frame_count", 0),
                    "lightweight": payload.get("lightweight", False),
                }
                yield _sse_msg(data)
                if not payload.get("generation_pending", False):
                    # Generation finished — send final state and close
                    return
                # Wait for next state change or timeout after 3 seconds
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
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _sse_msg(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


# ── SSE stream for video cleaning status ────────────────────────────────

@router.get("/api/reels/{draft_id}/clean-video-stream")
async def clean_video_stream(draft_id: str, _: str = Depends(_resolve_init_data)):
    """Server-Sent Events stream for video task progress (clean or compose)."""
    from bot.services import video_task_worker
    from bot.services.video_task_store import estimate_time_seconds

    async def _event_generator():
        evt = video_task_worker.get_event(draft_id)
        try:
            for _ in range(300):  # max ~10 minutes
                live = video_task_worker.live_status.get(draft_id)
                if not live:
                    # Check legacy in-memory
                    status = _clean_status.get(draft_id)
                    if not status:
                        draft = await serialize_reels_draft(draft_id)
                        if not draft:
                            yield _sse_msg({"error": "not_found"})
                            return
                        p = draft.get("payload", {}) if isinstance(draft, dict) else {}
                        if p.get("cleaning_status") == "completed":
                            yield _sse_msg({"draft_id": draft_id, "status": "completed", "result": p.get("cleaning_result")})
                            return
                        yield _sse_msg({"draft_id": draft_id, "status": "not_started"})
                        return
                    live = status

                msg = {
                    "draft_id": draft_id,
                    "status": live.get("status", "unknown"),
                    "step": live.get("step", ""),
                    "progress": live.get("progress", 0),
                }
                if live.get("error"):
                    msg["error"] = live["error"]
                if live.get("result"):
                    msg["result"] = live["result"]
                vid_dur = live.get("video_duration")
                if vid_dur:
                    msg["estimated_seconds"] = estimate_time_seconds(
                        live.get("task_type", "clean"), vid_dur,
                    )

                yield _sse_msg(msg)
                if live.get("status") in ("completed", "failed"):
                    return
                evt.clear()
                try:
                    await asyncio.wait_for(evt.wait(), timeout=2.0)
                except asyncio.TimeoutError:
                    pass
        finally:
            pass

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


# ── Split clips ─────────────────────────────────────────────────────────

_split_status: dict[str, dict] = {}
_split_logger = logging.getLogger(__name__ + ".split_clips")


async def _run_split_clips_task(draft_id: str) -> None:
    """Background task: split video into individual clips using stored intervals."""
    import asyncio
    from pathlib import Path

    from bot.services.reels_video import VIDEO_DIR

    try:
        _split_status[draft_id] = {"status": "running", "error": None}

        draft = await _get_draft(draft_id)
        if not draft:
            raise ValueError("Draft not found")

        payload = dict(draft.payload)
        video_filename = str(payload.get("video_filename") or "").strip()
        keep_intervals = payload.get("keep_intervals") or []

        if not video_filename:
            raise ValueError("No video uploaded")
        if not keep_intervals:
            raise ValueError("No intervals stored — run cleaning first")

        video_path = VIDEO_DIR / draft_id / video_filename
        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")

        output_dir = VIDEO_DIR / draft_id / "clips"

        from bot.services.video_processor.config import ProcessorConfig
        from bot.services.video_processor.filter_engine import Interval
        from bot.services.video_processor.splitter import group_intervals_into_clips, run_split

        loop = asyncio.get_running_loop()

        intervals = [Interval(start=s, end=e) for s, e in keep_intervals]
        config = ProcessorConfig(
            input_file=str(video_path),
            output_path=str(output_dir),
            mode="split",
        )

        output_dir.mkdir(parents=True, exist_ok=True)
        clips_data = group_intervals_into_clips(intervals, config)
        clip_files = await loop.run_in_executor(
            None, run_split, video_path, clips_data, output_dir, config,
        )

        split_clips = []
        for clip_file, clip_group in zip(clip_files, clips_data):
            start = round(clip_group[0].start, 1)
            end = round(clip_group[-1].end, 1)
            split_clips.append({
                "filename": f"clips/{Path(clip_file).name}",
                "start": start,
                "end": end,
            })

        payload["split_clips"] = split_clips
        payload["split_status"] = "completed"
        await _update_draft(draft_id, payload=payload)

        _split_status[draft_id] = {"status": "completed", "error": None}
        _split_logger.info("Split into %d clips for draft %s", len(split_clips), draft_id)

    except Exception as exc:
        _split_logger.error("Split failed for draft %s: %s", draft_id, exc, exc_info=True)
        _split_status[draft_id] = {"status": "failed", "error": str(exc)}
        try:
            draft = await _get_draft(draft_id)
            if draft:
                p = dict(draft.payload)
                p["split_status"] = "failed"
                await _update_draft(draft_id, payload=p)
        except Exception:
            pass


@router.post("/api/reels/{draft_id}/split-clips")
async def split_reels_clips(
    draft_id: str,
    background_tasks: BackgroundTasks,
    _: None = Depends(_require_auth),
):
    """Split cleaned video into individual clips for download."""
    draft = await serialize_reels_draft(draft_id)
    if not draft:
        raise HTTPException(404, "Reel not found")

    p = draft.get("payload", {}) if isinstance(draft, dict) else {}
    if not p.get("keep_intervals"):
        raise HTTPException(400, "No intervals — run video cleaning first")

    if _split_status.get(draft_id, {}).get("status") == "running":
        return JSONResponse(status_code=409, content={"detail": "split_already_running"})

    _split_status[draft_id] = {"status": "pending", "error": None}
    background_tasks.add_task(_run_split_clips_task, draft_id)
    return JSONResponse(status_code=202, content={"draft_id": draft_id, "status": "pending"})


@router.get("/api/reels/{draft_id}/split-clips-status")
async def split_clips_status(
    draft_id: str,
    _: None = Depends(_require_auth),
):
    """Check split clips status."""
    status = _split_status.get(draft_id)
    if not status:
        draft = await serialize_reels_draft(draft_id)
        if not draft:
            raise HTTPException(404, "Reel not found")
        p = draft.get("payload", {}) if isinstance(draft, dict) else {}
        s = p.get("split_status", "")
        if s == "completed":
            return {"draft_id": draft_id, "status": "completed"}
        return {"draft_id": draft_id, "status": "not_started"}
    return {"draft_id": draft_id, "status": status["status"], "error": status.get("error")}
