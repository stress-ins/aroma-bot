from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException

from bot.services.miniapp_references import (
    enrich_reference_card,
    get_reference_card,
    list_reference_cards,
    list_reference_cards_missing_description,
    list_reference_cards_with_placeholder_images,
    update_reference_card,
)
from config import settings
from bot.services.daily_oil import get_daily_oil
from ..auth import _require_reference_access, _telegram_user_id_from_init_data, _verify_init_data
from ..models import AromaCardPayload

router = APIRouter()


@router.get("/api/references/daily-oil")
async def daily_oil_endpoint(_: int = Depends(_require_reference_access)):
    """Return today's daily oil card."""
    oil = await get_daily_oil()
    if not oil:
        raise HTTPException(status_code=404, detail="no_daily_oil")
    return oil


@router.get("/api/references/access")
async def references_access(x_telegram_init_data: str | None = Header(default=None)):
    if not x_telegram_init_data or not _verify_init_data(x_telegram_init_data):
        return {"allowed": False}
    user_id = _telegram_user_id_from_init_data(x_telegram_init_data)
    return {
        "allowed": bool(user_id in settings.miniapp_aroma_allowed_user_id_set if user_id is not None else False),
        "user_id": user_id,
    }


@router.get("/api/references/audit")
async def references_audit(category: str = "aroma", _: int = Depends(_require_reference_access)):
    """Return cards with empty description field for content audit."""
    return {"items": await list_reference_cards_missing_description(category)}


@router.get("/api/references/images/audit")
async def references_images_audit(category: str = "aroma", _: int = Depends(_require_reference_access)):
    """Return cards with SVG placeholder images (dry-run view for image generation)."""
    return {"items": await list_reference_cards_with_placeholder_images(category)}


@router.get("/api/references/{category}")
async def references_list(category: str, _: int = Depends(_require_reference_access)):
    return {"items": await list_reference_cards(category)}


@router.get("/api/references/{category}/{slug}")
async def reference_detail(category: str, slug: str, _: int = Depends(_require_reference_access)):
    card = await get_reference_card(category, slug)
    if not card:
        raise HTTPException(status_code=404, detail="reference_not_found")
    return card


@router.put("/api/references/{category}/{slug}")
async def reference_update(
    category: str, slug: str, payload: AromaCardPayload, _: int = Depends(_require_reference_access)
):
    card = await update_reference_card(category, slug, payload.model_dump())
    if not card:
        raise HTTPException(status_code=404, detail="reference_not_found")
    return card


@router.post("/api/references/{category}/{slug}/expert-fill")
async def reference_expert_fill(category: str, slug: str, _: int = Depends(_require_reference_access)):
    if not settings.anthropic_api_key:
        raise HTTPException(status_code=400, detail="anthropic_not_configured")
    card = await enrich_reference_card(category, slug)
    if not card:
        raise HTTPException(status_code=404, detail="reference_not_found")
    return card
