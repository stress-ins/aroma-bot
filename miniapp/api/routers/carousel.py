from __future__ import annotations

import asyncio

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse

from bot.services.carousel_assets import (
    delete_carousel_slide_version,
    extract_images_from_pptx,
    load_carousel_slide_images,
    regenerate_carousel_slide_asset,
    save_carousel_slide_asset,
    select_carousel_slide_version,
    update_carousel_slide_note,
    update_carousel_slide_text,
)
from bot.handlers.carousel import _build_pptx
from bot.services.drafts_store import DraftRecord, get_draft, update_draft
from bot.services.draft_revisions_store import create_revision
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
async def get_carousel(draft: DraftRecord = Depends(require_draft("carousel"))):
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
        raise HTTPException(status_code=400, detail=str(exc))

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
