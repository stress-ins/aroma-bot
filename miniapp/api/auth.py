from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
import urllib.parse
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, Query

from bot.services.subscription_store import (
    TIER_RANK,
    check_daily_limit,
    effective_tier,
    get_or_create_user,
    increment_daily_usage,
)
from config import settings

logger = logging.getLogger(__name__)

# Reject initData tokens older than 24 hours to prevent replay attacks.
_AUTH_DATE_MAX_AGE = 86400


def _verify_init_data(init_data: str) -> bool:
    """Validate Telegram WebApp initData: HMAC-SHA256 signature + auth_date freshness."""
    if os.getenv("AROMA_BYPASS_AUTH") == "1" and os.getenv("AROMA_ENV", "production") in ("test", "dev"):
        return True
    try:
        parsed = dict(urllib.parse.parse_qsl(init_data, strict_parsing=True))
        received_hash = parsed.pop("hash", "")
        # Freshness check — reject tokens older than 24 hours
        auth_date = int(parsed.get("auth_date", 0))
        if time.time() - auth_date > _AUTH_DATE_MAX_AGE:
            return False
        check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
        secret_key = hmac.new(b"WebAppData", settings.telegram_bot_token.encode(), hashlib.sha256).digest()
        expected_hash = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected_hash, received_hash)
    except Exception:
        logger.warning("initData verification failed", exc_info=True)
        return False


def _telegram_user_id_from_init_data(init_data: str) -> int | None:
    try:
        parsed = dict(urllib.parse.parse_qsl(init_data, strict_parsing=True))
        raw_user = parsed.get("user", "")
        if not raw_user:
            return None
        payload = json.loads(raw_user)
        user_id = payload.get("id")
        return int(user_id) if user_id is not None else None
    except Exception:
        logger.warning("Failed to parse user_id from initData", exc_info=True)
        return None


def _telegram_username_from_init_data(init_data: str) -> str:
    try:
        parsed = dict(urllib.parse.parse_qsl(init_data, strict_parsing=True))
        raw_user = parsed.get("user", "")
        if not raw_user:
            return ""
        payload = json.loads(raw_user)
        return str(payload.get("username", ""))
    except Exception:
        return ""


def _require_auth(x_telegram_init_data: str | None = Header(default=None)) -> None:
    """FastAPI dependency: validate Telegram initData header on mutating endpoints."""
    if os.getenv("AROMA_BYPASS_AUTH") == "1" and os.getenv("AROMA_ENV", "production") in ("test", "dev"):
        return
    if not x_telegram_init_data or not _verify_init_data(x_telegram_init_data):
        raise HTTPException(status_code=403, detail="forbidden")


def _resolve_init_data(
    x_telegram_init_data: str | None = Header(default=None),
    init_data: str | None = Query(default=None),
) -> str:
    if os.getenv("AROMA_BYPASS_AUTH") == "1" and os.getenv("AROMA_ENV", "production") in ("test", "dev"):
        return x_telegram_init_data or init_data or ""
    candidate = x_telegram_init_data or init_data
    if not candidate or not _verify_init_data(candidate):
        raise HTTPException(status_code=403, detail="forbidden")
    return candidate


def _require_reference_access(x_telegram_init_data: str | None = Header(default=None)) -> int:
    if os.getenv("AROMA_BYPASS_AUTH") == "1" and os.getenv("AROMA_ENV", "production") in ("test", "dev"):
        return settings.miniapp_aroma_allowed_user_id_set.copy().pop() if settings.miniapp_aroma_allowed_user_id_set else 12345
    if not x_telegram_init_data or not _verify_init_data(x_telegram_init_data):
        raise HTTPException(status_code=403, detail="forbidden")
    user_id = _telegram_user_id_from_init_data(x_telegram_init_data)
    if user_id is None or user_id not in settings.miniapp_aroma_allowed_user_id_set:
        raise HTTPException(status_code=403, detail="reference_access_denied")
    return user_id


def _require_webhook_auth(x_webhook_secret: str | None = Header(default=None)) -> None:
    """For n8n webhook calls — validates X-Webhook-Secret header instead of Telegram initData."""
    expected = settings.n8n_webhook_secret
    if not expected or not x_webhook_secret or not hmac.compare_digest(x_webhook_secret, expected):
        raise HTTPException(status_code=403, detail="forbidden")


async def _resolve_telegram_id(
    x_telegram_init_data: str | None = Header(default=None),
) -> int:
    """FastAPI dependency: validate auth and return telegram_id as int."""
    if not x_telegram_init_data or not _verify_init_data(x_telegram_init_data):
        raise HTTPException(status_code=403, detail="forbidden")
    user_id = _telegram_user_id_from_init_data(x_telegram_init_data)
    if user_id is None:
        raise HTTPException(status_code=403, detail="forbidden")
    from bot.services.claude_client import current_telegram_id
    current_telegram_id.set(user_id)
    return user_id


@dataclass
class TelegramUser:
    telegram_id: int
    username: str


async def _resolve_telegram_user(
    x_telegram_init_data: str | None = Header(default=None),
) -> TelegramUser:
    """FastAPI dependency: validate auth and return telegram_id + username."""
    if not x_telegram_init_data or not _verify_init_data(x_telegram_init_data):
        raise HTTPException(status_code=403, detail="forbidden")
    user_id = _telegram_user_id_from_init_data(x_telegram_init_data)
    if user_id is None:
        raise HTTPException(status_code=403, detail="forbidden")
    username = _telegram_username_from_init_data(x_telegram_init_data)
    from bot.services.claude_client import current_telegram_id
    current_telegram_id.set(user_id)
    return TelegramUser(telegram_id=user_id, username=username)


def require_tier(min_tier: str):
    """Factory: returns a FastAPI dependency that enforces minimum subscription tier."""
    async def _dep(telegram_id: int = Depends(_resolve_telegram_id)) -> int:
        user = await get_or_create_user(telegram_id)
        tier = await effective_tier(user)
        if TIER_RANK.get(tier, 0) < TIER_RANK.get(min_tier, 0):
            raise HTTPException(
                status_code=402,
                detail={"error": "paywall", "tier_required": min_tier},
            )
        return telegram_id
    return _dep


async def _check_content_limit(telegram_id: int = Depends(_resolve_telegram_id)) -> int:
    """FastAPI dependency: enforce daily content creation limit for free-tier users."""
    user = await get_or_create_user(telegram_id)
    tier = await effective_tier(user)
    if tier == "free":
        used, max_allowed = await check_daily_limit(telegram_id)
        if used >= max_allowed:
            from bot.handlers.monitor import notify_owner_throttled

            notify_owner_throttled(
                f"⚠️ <b>Daily limit hit</b>\n"
                f"User: <code>{telegram_id}</code>\n"
                f"Used: {used}/{max_allowed}\n"
                f"Tier: free",
                dedup_key=f"daily_limit:{telegram_id}",
                cooldown=21600,
            )
            raise HTTPException(
                status_code=429,
                detail={"error": "daily_limit", "used": used, "max": max_allowed},
            )
    await increment_daily_usage(telegram_id)
    return telegram_id


# ---------------------------------------------------------------------------
# Team context resolution
# ---------------------------------------------------------------------------

@dataclass
class TeamContext:
    telegram_id: int
    team_id: str
    role: str  # owner/editor/viewer


async def _resolve_team_context(
    telegram_id: int = Depends(_resolve_telegram_id),
    x_team_id: str | None = Header(default=None),
) -> TeamContext:
    """Resolve team context from X-Team-Id header (or auto-create default team)."""
    from bot.services.team_store import get_default_team_with_role, get_member_role

    if x_team_id:
        role = await get_member_role(x_team_id, telegram_id)
        if not role:
            raise HTTPException(status_code=403, detail="not_a_team_member")
        return TeamContext(telegram_id=telegram_id, team_id=x_team_id, role=role)

    # No team header — single query for default team + role
    team, role = await get_default_team_with_role(telegram_id)
    return TeamContext(telegram_id=telegram_id, team_id=team.team_id, role=role)


def require_team_role(min_role: str):
    """Factory: returns FastAPI dependency that checks team membership and minimum role."""
    async def _dep(ctx: TeamContext = Depends(_resolve_team_context)) -> TeamContext:
        from bot.services.team_store import has_role

        if not has_role(ctx.role, min_role):
            raise HTTPException(
                status_code=403,
                detail={"error": "insufficient_role", "required": min_role, "current": ctx.role},
            )
        return ctx
    return _dep
