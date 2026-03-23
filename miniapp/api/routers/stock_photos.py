"""Stock photo search, selection, and user photo upload endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from pydantic import BaseModel

from bot.services.content_assets import ext_for_format, save_content_photo
from bot.services.drafts_store import get_draft, update_draft
from bot.services.image_validation import validate_uploaded_photo
from bot.services.stock_photos import download_stock_photo, search_stock_photos
from config import Settings
from ..auth import _require_auth

log = logging.getLogger(__name__)
router = APIRouter()

_settings = Settings()


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class StockPhotoSelectPayload(BaseModel):
    draft_id: str
    photo_id: str
    source: str  # "unsplash" | "pexels"
    url: str
    photographer: str = ""
    photographer_url: str = ""
    slide_index: int = -1  # -1 = main image, 0+ = carousel slide


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/api/stock-photos/search")
async def search_stock(
    keywords: str = Query(..., description="Comma-separated keywords"),
    orientation: str = Query(default="portrait"),
    _: None = Depends(_require_auth),
) -> dict:
    """Search Unsplash + Pexels for stock photos."""
    kw_list = [k.strip() for k in keywords.split(",") if k.strip()]
    if not kw_list:
        raise HTTPException(status_code=400, detail="keywords required")

    photos = await search_stock_photos(
        kw_list,
        orientation=orientation,
        unsplash_key=_settings.unsplash_access_key,
        pexels_key=_settings.pexels_api_key,
    )
    return {
        "photos": [p.to_dict() for p in photos],
        "keywords_used": " ".join(kw_list[:4]),
    }


@router.post("/api/stock-photos/select")
async def select_stock_photo(
    body: StockPhotoSelectPayload,
    _: None = Depends(_require_auth),
) -> dict:
    """Download a stock photo, save to assets, update draft payload."""
    draft = await get_draft(body.draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="draft_not_found")

    # Download photo
    image_bytes = await download_stock_photo(
        body.url,
        source=body.source,
        unsplash_key=_settings.unsplash_access_key,
    )

    attribution = f"Photo by {body.photographer} on {body.source.capitalize()}"
    asset = save_content_photo(
        body.draft_id,
        image_bytes,
        source=body.source,
        photographer=body.photographer,
        photographer_url=body.photographer_url,
        attribution=attribution,
    )

    # Update draft payload
    payload = dict(draft.payload or {})
    if body.slide_index >= 0 and draft.kind == "carousel":
        # Per-slide for carousel
        slide_images = list(payload.get("slide_images") or [])
        while len(slide_images) <= body.slide_index:
            slide_images.append(None)
        slide_images[body.slide_index] = asset
        payload["slide_images"] = slide_images
    else:
        payload["image"] = asset

    await update_draft(body.draft_id, payload=payload)
    return {"ok": True, "asset": asset}


@router.post("/api/drafts/{draft_id}/upload-photo")
async def upload_draft_photo(
    draft_id: str,
    file: UploadFile = File(...),
    slide_index: int = Query(default=-1),
    _: None = Depends(_require_auth),
) -> dict:
    """Upload a user photo with validation, save to assets, update draft."""
    draft = await get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="draft_not_found")

    image_bytes = await file.read()

    # Validate
    validation = validate_uploaded_photo(image_bytes)
    if not validation.ok:
        return {
            "ok": False,
            "validation": validation.to_dict(),
        }

    ext = ext_for_format(validation.format)
    asset = save_content_photo(
        draft_id,
        image_bytes,
        source="upload",
        ext=ext,
    )

    # Update draft payload
    payload = dict(draft.payload or {})
    if slide_index >= 0 and draft.kind == "carousel":
        slide_images = list(payload.get("slide_images") or [])
        while len(slide_images) <= slide_index:
            slide_images.append(None)
        slide_images[slide_index] = asset
        payload["slide_images"] = slide_images
    else:
        payload["image"] = asset

    await update_draft(draft_id, payload=payload)
    return {
        "ok": True,
        "asset": asset,
        "validation": validation.to_dict(),
    }
