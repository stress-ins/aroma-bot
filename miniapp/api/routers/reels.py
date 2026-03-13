from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from bot.services.drafts_store import DraftModel, get_draft
from bot.services.miniapp_reels import (
    build_reels_export_payload,
    list_reels_drafts,
    regenerate_reels_storyboard,
    serialize_reels_draft,
    update_reels_frame_fields,
    update_reels_frame_note,
    update_reels_frame_prompt,
    update_reels_scenario,
)
from bot.services.reels_assets import regenerate_reels_frame_asset
from ..auth import _require_auth
from ..deps import require_draft
from ..generation import complete_reels_regenerate_all, set_generation_state
from ..models import ReelsFrameFieldsPayload, ReelsFrameNotePayload, ReelsFramePromptPayload, ReelsScenarioPayload

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


@router.post("/api/reels/{draft_id}/frames/{frame_index}/regenerate")
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


@router.post("/api/reels/{draft_id}/storyboard/regenerate")
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


@router.post("/api/reels/{draft_id}/frames/regenerate-all")
async def reels_frames_regenerate_all(
    background_tasks: BackgroundTasks,
    draft: DraftModel = Depends(require_draft("reels")),
):
    draft_id = draft.draft_id
    await set_generation_state(
        draft_id, pending=True, stage="images", message="Перегенерирую все кадры рилса."
    )
    background_tasks.add_task(complete_reels_regenerate_all, draft_id)
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
