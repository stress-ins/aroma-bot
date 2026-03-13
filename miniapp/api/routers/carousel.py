from __future__ import annotations

import asyncio

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse

from bot.services.carousel_assets import (
    delete_carousel_slide_version,
    load_carousel_slide_images,
    regenerate_carousel_slide_asset,
    select_carousel_slide_version,
    update_carousel_slide_note,
    update_carousel_slide_text,
)
from bot.handlers.carousel import _build_pptx
from bot.services.drafts_store import DraftModel, get_draft
from bot.services.miniapp_presenter import serialize_draft
from ..auth import _require_auth, _resolve_init_data
from ..deps import require_draft
from ..generation import complete_carousel_regenerate_all, set_generation_state
from ..models import (
    CarouselSlideNotePayload,
    CarouselSlideRegeneratePayload,
    CarouselSlideTextPayload,
)

router = APIRouter()


@router.get("/api/carousel/{draft_id}")
async def get_carousel(draft: DraftModel = Depends(require_draft("carousel"))):
    return await serialize_draft(draft)


@router.post("/api/carousel/{draft_id}/slides/{slide_index}/regenerate")
async def regenerate_carousel_slide(
    draft_id: str,
    slide_index: int,
    payload: CarouselSlideRegeneratePayload,
    _: None = Depends(_require_auth),
):
    updated_payload = await regenerate_carousel_slide_asset(draft_id, slide_index, note=payload.note)
    if updated_payload is None:
        raise HTTPException(status_code=404, detail="carousel_slide_not_found")
    draft = await get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="carousel_not_found")
    return await serialize_draft(draft)


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


@router.post("/api/carousel/{draft_id}/regenerate-all")
async def regenerate_carousel_all(
    background_tasks: BackgroundTasks,
    draft: DraftModel = Depends(require_draft("carousel")),
):
    await set_generation_state(
        draft.draft_id, pending=True, stage="images", message="Перегенерирую все картинки в карусели."
    )
    background_tasks.add_task(complete_carousel_regenerate_all, draft.draft_id)
    refreshed = await get_draft(draft.draft_id)
    if not refreshed:
        raise HTTPException(status_code=404, detail="carousel_not_found")
    return await serialize_draft(refreshed)


@router.get("/api/carousel/{draft_id}/pptx")
async def carousel_pptx_export(draft_id: str, _: str = Depends(_resolve_init_data)):
    # Uses _resolve_init_data (not _require_auth) — cannot use require_draft dep here
    draft = await get_draft(draft_id)
    if not draft or draft.kind != "carousel":
        raise HTTPException(status_code=404, detail="carousel_not_found")
    slides = list(draft.payload.get("slides", []))
    images = load_carousel_slide_images(draft_id, list(draft.payload.get("slide_images", [])))
    pptx_bytes = await asyncio.get_running_loop().run_in_executor(None, _build_pptx, slides, images or None)
    return StreamingResponse(
        iter([pptx_bytes]),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f'attachment; filename="carousel_{draft_id}.pptx"'},
    )
