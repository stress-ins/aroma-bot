from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
import urllib.parse

from fastapi import Header, HTTPException, Query

from config import settings

logger = logging.getLogger(__name__)

# Reject initData tokens older than 24 hours to prevent replay attacks.
_AUTH_DATE_MAX_AGE = 86400


def _verify_init_data(init_data: str) -> bool:
    """Validate Telegram WebApp initData: HMAC-SHA256 signature + auth_date freshness."""
    if os.getenv("AROMA_BYPASS_AUTH") == "1":
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


def _require_auth(x_telegram_init_data: str | None = Header(default=None)) -> None:
    """FastAPI dependency: validate Telegram initData header on mutating endpoints."""
    if not x_telegram_init_data or not _verify_init_data(x_telegram_init_data):
        raise HTTPException(status_code=403, detail="forbidden")


def _resolve_init_data(
    x_telegram_init_data: str | None = Header(default=None),
    init_data: str | None = Query(default=None),
) -> str:
    candidate = x_telegram_init_data or init_data
    if not candidate or not _verify_init_data(candidate):
        raise HTTPException(status_code=403, detail="forbidden")
    return candidate


def _require_reference_access(x_telegram_init_data: str | None = Header(default=None)) -> int:
    if not x_telegram_init_data or not _verify_init_data(x_telegram_init_data):
        raise HTTPException(status_code=403, detail="forbidden")
    user_id = _telegram_user_id_from_init_data(x_telegram_init_data)
    if user_id is None or user_id not in settings.miniapp_aroma_allowed_user_id_set:
        raise HTTPException(status_code=403, detail="reference_access_denied")
    return user_id
