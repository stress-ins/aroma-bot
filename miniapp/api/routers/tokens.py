"""Platform token management — view, refresh, update (called by n8n and Mini App)."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException

from bot.services.mentions_store import get_token, list_expiring_tokens, list_tokens, upsert_token
from config import settings
from ..auth import TeamContext, _require_auth, _require_webhook_auth, require_team_role
from ..models import TokenStatusResponse, TokenUpdatePayload

logger = logging.getLogger(__name__)

router = APIRouter()

_REFRESH_URLS = {
    "threads": "https://graph.threads.net/refresh_access_token",
    "instagram": "https://graph.instagram.com/refresh_access_token",
}
_GRANT_TYPES = {
    "threads": "th_refresh_token",
    "instagram": "ig_refresh_token",
}


def _serialize_token(t) -> dict:
    return {
        "platform": t.platform,
        "has_token": bool(t.access_token),
        "expires_at": t.expires_at.isoformat() if t.expires_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


@router.get("/api/tokens/status")
async def tokens_status(ctx: TeamContext = Depends(require_team_role("owner"))):
    tokens = await list_tokens(team_id=ctx.team_id)
    return {"tokens": [_serialize_token(t) for t in tokens]}


@router.get("/api/tokens/expiring")
async def tokens_expiring(days: int = 7, _: None = Depends(_require_webhook_auth)):
    tokens = await list_expiring_tokens(days=days)
    return {"tokens": [_serialize_token(t) for t in tokens]}


@router.patch("/api/tokens/{platform}")
async def update_token(
    platform: str,
    payload: TokenUpdatePayload,
    _: None = Depends(_require_webhook_auth),
):
    if platform not in ("threads", "instagram", "canva", "youtube"):
        raise HTTPException(status_code=400, detail="unsupported_platform")

    expires_at: datetime | None = None
    if payload.expires_at:
        try:
            expires_at = datetime.fromisoformat(payload.expires_at)
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
        except ValueError:
            raise HTTPException(status_code=400, detail="invalid_expires_at_format")

    token = await upsert_token(platform, payload.access_token, expires_at)
    return _serialize_token(token)


@router.post("/api/tokens/{platform}/refresh")
async def refresh_token(platform: str, _: None = Depends(_require_webhook_auth)):
    if platform not in ("threads", "instagram", "canva", "youtube"):
        raise HTTPException(status_code=400, detail="unsupported_platform")

    token_record = await get_token(platform)
    if not token_record or not token_record.access_token:
        raise HTTPException(status_code=404, detail="no_token_stored")

    if platform == "canva":
        return await _refresh_canva(token_record)

    if platform == "youtube":
        return await _refresh_youtube(token_record)

    refresh_url = _REFRESH_URLS[platform]
    grant_type = _GRANT_TYPES[platform]

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                refresh_url,
                params={
                    "grant_type": grant_type,
                    "access_token": token_record.access_token,
                },
            )
            response.raise_for_status()
            data = response.json()
    except Exception as exc:
        logger.error("Token refresh failed for %s: %s", platform, exc)
        raise HTTPException(status_code=502, detail=f"refresh_failed: {exc}")

    new_token = data.get("access_token", token_record.access_token)
    expires_at: datetime | None = None
    if "expires_in" in data:
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(data["expires_in"]))

    updated = await upsert_token(platform, new_token, expires_at)
    return {**_serialize_token(updated), "refreshed": True}


async def _refresh_youtube(token_record) -> dict:
    """Refresh YouTube/Google access token using refresh_token."""
    if not token_record.refresh_token:
        raise HTTPException(
            status_code=400,
            detail="no_refresh_token — переподключите YouTube в Настройки → Аккаунты",
        )
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(status_code=500, detail="google_client_id/secret not configured")

    try:
        from bot.services.social_oauth import refresh_youtube_token
        result = refresh_youtube_token(
            refresh_token=token_record.refresh_token,
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
        )
    except Exception as exc:
        logger.error("YouTube token refresh failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"refresh_failed: {exc}")

    expires_at = None
    if result.get("expires_in"):
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(result["expires_in"]))

    updated = await upsert_token(
        "youtube",
        str(result["access_token"]),
        expires_at,
        refresh_token=str(result.get("refresh_token", "")),
    )
    return {**_serialize_token(updated), "refreshed": True}


async def _refresh_canva(token_record) -> dict:
    """Refresh Canva token using refresh_token + Basic auth."""
    if not token_record.refresh_token:
        raise HTTPException(
            status_code=400,
            detail="no_refresh_token — переподключите Canva в Настройки → Аккаунты",
        )
    if not settings.canva_client_id or not settings.canva_client_secret:
        raise HTTPException(status_code=500, detail="canva_client_id/secret not configured")

    try:
        from bot.services.social_oauth import refresh_canva_token
        result = refresh_canva_token(
            refresh_token=token_record.refresh_token,
            client_id=settings.canva_client_id,
            client_secret=settings.canva_client_secret,
        )
    except Exception as exc:
        logger.error("Canva token refresh failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"refresh_failed: {exc}")

    expires_at = None
    if result.get("expires_in"):
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(result["expires_in"]))

    updated = await upsert_token(
        "canva",
        str(result["access_token"]),
        expires_at,
        refresh_token=str(result.get("refresh_token", "")),
    )
    return {**_serialize_token(updated), "refreshed": True}
