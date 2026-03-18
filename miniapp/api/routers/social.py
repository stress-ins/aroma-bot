"""Social accounts — connect status and OAuth URL generation for Mini App."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Header, HTTPException

from bot.services.mentions_store import get_token, list_tokens
from bot.services.social_oauth import (
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

_PLATFORMS = ("threads", "instagram")


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
        user_id_token = await get_token(f"{acc['platform']}_user_id")
        if user_id_token and user_id_token.access_token:
            acc["username"] = user_id_token.access_token
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
    else:
        url = build_instagram_authorize_url(
            client_id=settings.instagram_app_id,
            redirect_uri=INSTAGRAM_REDIRECT_URI,
            state=state,
        )

    return {"url": url, "platform": platform}
