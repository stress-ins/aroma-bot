from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

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
from bot.services.reels_assets import regenerate_reels_frame_asset
from ..auth import _require_auth, require_tier
from ..deps import require_draft
from ..generation import (
    complete_reels_regenerate_all,
    complete_reels_v2_regen_caption,
    complete_reels_v2_regen_concept_only,
    complete_reels_v2_regen_frame,
    complete_reels_v2_regen_scenario_only,
    set_generation_state,
)
from ..models import (
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
    draft = await serialize_reels_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="reels_not_found")
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
    draft = await serialize_reels_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="reels_not_found")
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


@router.post("/api/reels/{draft_id}/scenario")
async def reels_scenario_update(
    draft_id: str,
    payload: ReelsScenarioPayload,
    _: None = Depends(_require_auth),
):
    draft = await update_reels_scenario(draft_id, payload.scenario, payload.concept)
    if not draft:
        raise HTTPException(status_code=404, detail="reels_not_found")
    return draft


@router.post("/api/reels/{draft_id}/storyboard/regenerate", dependencies=[Depends(require_tier("expert"))])
async def reels_storyboard_regenerate(
    draft_id: str,
    background_tasks: BackgroundTasks,
    _: None = Depends(_require_auth),
):
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
# Video pipeline: compose & status
# ---------------------------------------------------------------------------

_compose_logger = logging.getLogger(__name__ + ".compose")

# In-memory compose status tracker (lightweight; not persisted across restarts)
_compose_status: dict[str, dict] = {}


async def _run_compose_task(draft_id: str) -> None:
    """Background task that runs the video pipeline and updates status."""
    from bot.services.video_pipeline import compose_reel

    try:
        _compose_status[draft_id] = {"status": "running", "error": None, "result": None}
        result = await compose_reel(draft_id)
        _compose_status[draft_id] = {"status": "completed", "error": None, "result": result}
        _compose_logger.info("Compose completed for draft %s", draft_id)
    except Exception as exc:
        _compose_logger.error("Compose failed for draft %s: %s", draft_id, exc, exc_info=True)
        _compose_status[draft_id] = {"status": "failed", "error": str(exc), "result": None}


@router.post("/api/reels/{draft_id}/compose", dependencies=[Depends(require_tier("expert"))])
async def compose_reel_video(
    draft_id: str,
    background_tasks: BackgroundTasks,
    _: None = Depends(_require_auth),
):
    """Trigger video composition for a reels draft.

    Runs the full pipeline (frames -> video -> voiceover -> music -> final MP4)
    as a background task. Returns 202 Accepted immediately.
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

    _compose_status[draft_id] = {"status": "pending", "error": None, "result": None}
    background_tasks.add_task(_run_compose_task, draft_id)
    return JSONResponse(
        status_code=202,
        content={"draft_id": draft_id, "status": "pending", "message": "Video composition started"},
    )


@router.get("/api/reels/{draft_id}/compose-status")
async def compose_reel_status(
    draft_id: str,
    _: None = Depends(_require_auth),
):
    """Check video composition status for a reels draft."""
    status = _compose_status.get(draft_id)
    if not status:
        # Check if the draft already has a video
        draft = await serialize_reels_draft(draft_id)
        if not draft:
            raise HTTPException(status_code=404, detail="reels_not_found")
        payload = draft.get("payload", {})
        if isinstance(payload, dict) and payload.get("video_ready"):
            return {
                "draft_id": draft_id,
                "status": "completed",
                "video_path": payload.get("video_path"),
                "video_url": payload.get("video_url"),
            }
        return {"draft_id": draft_id, "status": "not_started"}

    response: dict = {"draft_id": draft_id, "status": status["status"]}
    if status["error"]:
        response["error"] = status["error"]
    if status["result"]:
        response["result"] = status["result"]
    return response
