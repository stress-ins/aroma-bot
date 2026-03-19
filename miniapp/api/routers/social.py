"""Social accounts — connect status, OAuth URL, and monitored accounts management."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from bot.services.brand_settings_store import get_brand_settings, update_brand_settings
from bot.services.mentions_store import get_token, list_tokens
from bot.services.social_oauth import (
    build_canva_authorize_url,
    build_instagram_authorize_url,
    build_oauth_state,
    build_threads_authorize_url,
)
from config import settings
from ..auth import TeamContext, _require_auth, _telegram_user_id_from_init_data, require_team_role

logger = logging.getLogger(__name__)
router = APIRouter()

THREADS_REDIRECT_URI = "https://oauth.aromara.ru/threads/callback"
INSTAGRAM_REDIRECT_URI = "https://oauth.aromara.ru/instagram/callback"
CANVA_REDIRECT_URI = "https://oauth.aromara.ru/canva/callback"

_PLATFORMS = ("threads", "instagram", "canva")


@router.get("/api/social/status")
async def social_status(ctx: TeamContext = Depends(require_team_role("owner"))):
    tokens = await list_tokens(team_id=ctx.team_id)
    token_map: dict[str, dict] = {}
    for t in tokens:
        token_map[t.platform] = {
            "has_token": bool(t.access_token),
            "expires_at": t.expires_at.isoformat() if t.expires_at else None,
            "updated_at": t.updated_at.isoformat() if t.updated_at else None,
        }

    accounts = []
    for platform in _PLATFORMS:
        info = token_map.get(platform, {})
        accounts.append({
            "platform": platform,
            "connected": info.get("has_token", False),
            "username": None,
            "expires_at": info.get("expires_at"),
            "updated_at": info.get("updated_at"),
        })
    for acc in accounts:
        username_token = await get_token(f"{acc['platform']}_username")
        if username_token and username_token.access_token:
            acc["username"] = username_token.access_token
    return {"accounts": accounts}


@router.get("/api/social/connect-url")
async def social_connect_url(
    platform: str,
    x_telegram_init_data: str | None = Header(default=None),
    _: None = Depends(_require_auth),
):
    if platform not in _PLATFORMS:
        raise HTTPException(status_code=400, detail="unsupported_platform")

    if platform == "threads" and (not settings.threads_app_id or not settings.threads_app_secret):
        raise HTTPException(status_code=400, detail="threads_not_configured")
    if platform == "instagram" and (not settings.instagram_app_id or not settings.instagram_app_secret):
        raise HTTPException(status_code=400, detail="instagram_not_configured")
    if platform == "canva" and (not settings.canva_client_id or not settings.canva_client_secret):
        raise HTTPException(status_code=400, detail="canva_not_configured")

    user_id = _telegram_user_id_from_init_data(x_telegram_init_data or "") or 0
    chat_id = user_id

    state = build_oauth_state(
        secret=settings.telegram_bot_token,
        service=platform,
        chat_id=chat_id,
        user_id=user_id,
    )

    if platform == "threads":
        url = build_threads_authorize_url(
            client_id=settings.threads_app_id,
            redirect_uri=THREADS_REDIRECT_URI,
            state=state,
        )
    elif platform == "canva":
        url = build_canva_authorize_url(
            client_id=settings.canva_client_id,
            redirect_uri=CANVA_REDIRECT_URI,
            state=state,
        )
    else:
        url = build_instagram_authorize_url(
            client_id=settings.instagram_app_id,
            redirect_uri=INSTAGRAM_REDIRECT_URI,
            state=state,
        )

    return {"url": url, "platform": platform}


# ---------------------------------------------------------------------------
# Monitored accounts management
# ---------------------------------------------------------------------------

_MAX_MONITORED_PER_PLATFORM = 20


class MonitoredAccountPayload(BaseModel):
    platform: str  # "instagram" | "threads"
    username: str


@router.get("/api/social/monitored-accounts")
async def list_monitored_accounts(
    ctx: TeamContext = Depends(require_team_role("viewer")),
):
    """List all monitored IG + Threads accounts for this team."""
    bs = await get_brand_settings(ctx.team_id)
    return {
        "instagram": bs.instagram_accounts or [],
        "threads": bs.threads_accounts or [],
    }


@router.post("/api/social/monitored-accounts")
async def add_monitored_account(
    payload: MonitoredAccountPayload,
    ctx: TeamContext = Depends(require_team_role("editor")),
):
    """Add a monitored account for this team."""
    if payload.platform not in ("instagram", "threads"):
        raise HTTPException(status_code=400, detail="unsupported_platform")

    username = payload.username.strip().lstrip("@")
    if not username:
        raise HTTPException(status_code=400, detail="empty_username")

    bs = await get_brand_settings(ctx.team_id)
    field = f"{payload.platform}_accounts"
    accounts: list = getattr(bs, field, None) or []

    # Check limit
    if len(accounts) >= _MAX_MONITORED_PER_PLATFORM:
        raise HTTPException(status_code=400, detail="max_accounts_reached")

    # Check duplicate
    if any(a.get("username", "").lower() == username.lower() for a in accounts):
        raise HTTPException(status_code=400, detail="already_monitored")

    new_entry = {"username": username, "status": "checking"}
    accounts.append(new_entry)
    await update_brand_settings(ctx.team_id, **{field: accounts})

    return {"added": new_entry, "total": len(accounts)}


@router.delete("/api/social/monitored-accounts/{platform}/{username}")
async def remove_monitored_account(
    platform: str,
    username: str,
    ctx: TeamContext = Depends(require_team_role("editor")),
):
    """Remove a monitored account."""
    if platform not in ("instagram", "threads"):
        raise HTTPException(status_code=400, detail="unsupported_platform")

    username_clean = username.strip().lstrip("@").lower()
    bs = await get_brand_settings(ctx.team_id)
    field = f"{platform}_accounts"
    accounts: list = getattr(bs, field, None) or []

    original_len = len(accounts)
    accounts = [a for a in accounts if a.get("username", "").lower() != username_clean]

    if len(accounts) == original_len:
        raise HTTPException(status_code=404, detail="account_not_found")

    await update_brand_settings(ctx.team_id, **{field: accounts})
    return {"removed": username_clean, "remaining": len(accounts)}


# ---------------------------------------------------------------------------
# Tracked hashtags for trend monitoring
# ---------------------------------------------------------------------------

_MAX_TRACKED_HASHTAGS = 30


class TrackedHashtagPayload(BaseModel):
    tag: str


@router.get("/api/social/tracked-hashtags")
async def list_tracked_hashtags(
    ctx: TeamContext = Depends(require_team_role("viewer")),
):
    bs = await get_brand_settings(ctx.team_id)
    return {"items": bs.tracked_hashtags or []}


@router.post("/api/social/tracked-hashtags")
async def add_tracked_hashtag(
    payload: TrackedHashtagPayload,
    ctx: TeamContext = Depends(require_team_role("editor")),
):
    tag = payload.tag.strip().lstrip("#").lower()
    if not tag:
        raise HTTPException(status_code=400, detail="empty_tag")

    bs = await get_brand_settings(ctx.team_id)
    tags: list = list(bs.tracked_hashtags or [])

    if len(tags) >= _MAX_TRACKED_HASHTAGS:
        raise HTTPException(status_code=400, detail="max_tags_reached")

    if tag in tags:
        raise HTTPException(status_code=400, detail="already_tracked")

    tags.append(tag)
    await update_brand_settings(ctx.team_id, tracked_hashtags=tags)
    return {"added": tag, "items": tags}


@router.delete("/api/social/tracked-hashtags/{tag}")
async def remove_tracked_hashtag(
    tag: str,
    ctx: TeamContext = Depends(require_team_role("editor")),
):
    tag_clean = tag.strip().lstrip("#").lower()
    bs = await get_brand_settings(ctx.team_id)
    tags: list = list(bs.tracked_hashtags or [])

    if tag_clean not in tags:
        raise HTTPException(status_code=404, detail="tag_not_found")

    tags.remove(tag_clean)
    await update_brand_settings(ctx.team_id, tracked_hashtags=tags)
    return {"removed": tag_clean, "items": tags}
