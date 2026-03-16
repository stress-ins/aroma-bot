"""User plan and promo code endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from bot.services.daily_oil import toggle_subscription
from bot.services.subscription_store import (
    FREE_DAILY_LIMIT,
    activate_promo,
    check_daily_limit,
    effective_tier,
    get_or_create_user,
)
from ..auth import _resolve_telegram_id

router = APIRouter()


class PromoActivateRequest(BaseModel):
    code: str


@router.get("/api/user/plan")
async def get_user_plan(telegram_id: int = Depends(_resolve_telegram_id)):
    user = await get_or_create_user(telegram_id)
    tier = await effective_tier(user)

    daily_used: int | None = None
    daily_max: int | None = None
    if tier == "free":
        used, max_allowed = await check_daily_limit(telegram_id)
        daily_used = used
        daily_max = max_allowed

    trial_ends_at = None
    if user.trial_ends_at is not None:
        trial_ends_at = user.trial_ends_at.isoformat() + "Z" if not user.trial_ends_at.isoformat().endswith("Z") else user.trial_ends_at.isoformat()

    return {
        "tier": user.tier,
        "effective_tier": tier,
        "trial_ends_at": trial_ends_at,
        "daily_cards_used": daily_used,
        "daily_cards_max": daily_max,
    }


@router.post("/api/promo/activate")
async def activate_promo_code(
    payload: PromoActivateRequest,
    telegram_id: int = Depends(_resolve_telegram_id),
):
    promo = await activate_promo(telegram_id, payload.code)
    if promo is None:
        raise HTTPException(status_code=404, detail="promo_not_found_or_expired")

    user = await get_or_create_user(telegram_id)
    tier = await effective_tier(user)
    ends_at = user.trial_ends_at.isoformat() + "Z" if user.trial_ends_at and not user.trial_ends_at.isoformat().endswith("Z") else (user.trial_ends_at.isoformat() if user.trial_ends_at else None)

    return {"tier": tier, "ends_at": ends_at}


@router.post("/api/user/daily-oil-subscription")
async def toggle_daily_oil_subscription(
    telegram_id: int = Depends(_resolve_telegram_id),
):
    """Toggle daily oil subscription for the user."""
    subscribed = await toggle_subscription(telegram_id)
    return {"daily_oil_subscribed": subscribed}
