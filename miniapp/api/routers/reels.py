from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, UploadFile
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
from bot.services.reels_assets import recover_frame_asset, regenerate_reels_frame_asset
from ..auth import _require_auth, require_tier
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
_clean_logger = logging.getLogger(__name__ + ".clean_video")


async def _run_clean_video_task(
    draft_id: str,
    min_pause_duration: float,
    silence_threshold_db: float,
) -> None:
    """Background task: run video_processor on uploaded video."""
    import asyncio

    from bot.services.reels_video import VIDEO_DIR

    try:
        _clean_status[draft_id] = {"status": "running", "error": None, "result": None}

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

        config = ProcessorConfig(
            input_file=str(video_path),
            output_path=str(output_dir),
            mode="single",
            min_pause_duration=min_pause_duration,
            silence_threshold_db=silence_threshold_db,
        )

        loop = asyncio.get_running_loop()
        proc_result = await loop.run_in_executor(None, process, config)

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
        await _update_draft(draft_id, payload=payload)

        _clean_status[draft_id] = {
            "status": "completed",
            "error": None,
            "result": payload["cleaning_result"],
        }
        _clean_logger.info("Video cleaning completed for draft %s", draft_id)

    except Exception as exc:
        _clean_logger.error(
            "Video cleaning failed for draft %s: %s", draft_id, exc, exc_info=True,
        )
        _clean_status[draft_id] = {"status": "failed", "error": str(exc), "result": None}
        try:
            draft = await _get_draft(draft_id)
            if draft:
                payload = dict(draft.payload)
                payload["cleaning_status"] = "failed"
                payload["cleaning_error"] = str(exc)
                await _update_draft(draft_id, payload=payload)
        except Exception:
            pass


@router.post("/api/reels/{draft_id}/clean-video")
async def clean_reels_video(
    draft_id: str,
    payload: CleanVideoPayload,
    background_tasks: BackgroundTasks,
    _: None = Depends(_require_auth),
):
    """Start video cleaning (silence removal) as a background task."""
    draft = await serialize_reels_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="reels_not_found")

    current = _clean_status.get(draft_id)
    if current and current["status"] == "running":
        return JSONResponse(
            status_code=409,
            content={"detail": "clean_already_running", "draft_id": draft_id},
        )

    _clean_status[draft_id] = {"status": "pending", "error": None, "result": None}
    background_tasks.add_task(
        _run_clean_video_task,
        draft_id,
        payload.min_pause_duration,
        payload.silence_threshold_db,
    )
    return JSONResponse(
        status_code=202,
        content={"draft_id": draft_id, "status": "pending"},
    )


@router.get("/api/reels/{draft_id}/clean-video-status")
async def clean_video_status(
    draft_id: str,
    _: None = Depends(_require_auth),
):
    """Check video cleaning status."""
    status = _clean_status.get(draft_id)
    if not status:
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

    response: dict = {"draft_id": draft_id, "status": status["status"]}
    if status["error"]:
        response["error"] = status["error"]
    if status["result"]:
        response["result"] = status["result"]
    return response
