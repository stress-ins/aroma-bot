"""Rate limiting middleware for the miniapp API.

Uses the ``limits`` library with in-memory storage.
Identifies users by Telegram user ID extracted from the auth header.

Tiers:
- Generation endpoints (LLM calls): 10 req/min per user
- Read-only (GET): 120 req/min per user
- Default (mutations): 60 req/min per user

Disable at runtime: set env ``AROMA_RATE_LIMIT_DISABLED=1``.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.parse

from limits import parse as parse_limit
from limits.storage import MemoryStorage
from limits.strategies import MovingWindowRateLimiter
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Storage and strategy (in-memory, resets on restart)
# ---------------------------------------------------------------------------

_storage = MemoryStorage()
_limiter = MovingWindowRateLimiter(_storage)

# Parsed limit objects
LIMIT_DEFAULT = parse_limit("60/minute")
LIMIT_GENERATION = parse_limit("20/minute")
LIMIT_READONLY = parse_limit("120/minute")

# Allowed users exempt from rate limiting (team members, not public users)
_EXEMPT_IDS: set[str] = set()


def _build_exempt_ids() -> set[str]:
    """Build exempt set from admin ID + allowed user IDs."""
    ids: set[str] = set()
    admin_raw = os.getenv("ADMIN_TELEGRAM_CHAT_ID", "")
    if admin_raw:
        for uid in admin_raw.split(","):
            if uid.strip():
                ids.add(f"tg:{uid.strip()}")
    try:
        from config import settings
        for uid in settings.miniapp_aroma_allowed_user_id_set:
            ids.add(f"tg:{uid}")
    except Exception:
        pass
    return ids


# ---------------------------------------------------------------------------
# Key function: extract Telegram user ID from X-Telegram-Init-Data header
# ---------------------------------------------------------------------------

def get_user_key(request: Request) -> str:
    """Return a rate-limit key based on Telegram user ID, falling back to IP."""
    init_data = request.headers.get("x-telegram-init-data", "")
    if init_data:
        try:
            parsed = dict(urllib.parse.parse_qsl(init_data, strict_parsing=True))
            raw_user = parsed.get("user", "")
            if raw_user:
                payload = json.loads(raw_user)
                uid = payload.get("id")
                if uid is not None:
                    return f"tg:{uid}"
        except Exception:
            pass
    # Fallback to client IP
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return f"ip:{forwarded.split(',')[0].strip()}"
    client = request.client
    return f"ip:{client.host}" if client else "ip:unknown"


# ---------------------------------------------------------------------------
# Path classification
# ---------------------------------------------------------------------------

def is_generation_path(path: str) -> bool:
    """Check if the request path corresponds to a generation (LLM) endpoint."""
    parts = path.strip("/").split("/")
    if len(parts) < 3 or parts[0] != "api":
        return False
    # /api/generate/* -- all generation create endpoints
    if parts[1] == "generate":
        return True
    # /api/<resource>/<id>/regenerate* or /api/<resource>/<id>/generate*
    if len(parts) >= 4 and ("regenerate" in parts[3] or "generate" in parts[3]):
        return True
    # /api/<resource>/<id>/slides/<idx>/regenerate
    if len(parts) >= 6 and "regenerate" in parts[5]:
        return True
    # /api/<resource>/<id>/frames/regenerate-all or storyboard/regenerate
    if len(parts) >= 5 and ("regenerate" in parts[4] or "generate" in parts[4]):
        return True
    return False


def _select_limit(request: Request):
    """Choose the appropriate limit based on request method and path."""
    path = request.url.path
    # Skip non-API paths (static files, HTML pages)
    if not path.startswith("/api/"):
        return None
    if request.method == "GET":
        return LIMIT_READONLY
    if is_generation_path(path):
        return LIMIT_GENERATION
    return LIMIT_DEFAULT


# ---------------------------------------------------------------------------
# 429 response builder
# ---------------------------------------------------------------------------

def _make_429_response(retry_after: int) -> Response:
    """Build a structured 429 response matching frontend expectations."""
    body = json.dumps({
        "detail": {
            "error": "rate_limit",
            "retry_after": retry_after,
        }
    })
    return Response(
        content=body,
        status_code=429,
        media_type="application/json",
        headers={"Retry-After": str(retry_after)},
    )


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class RateLimitMiddleware(BaseHTTPMiddleware):
    """Starlette middleware that enforces per-user rate limits on /api/ routes."""

    async def dispatch(self, request: Request, call_next):
        # Check env flag (allows disabling at runtime for tests)
        if os.getenv("AROMA_RATE_LIMIT_DISABLED") == "1":
            return await call_next(request)

        limit = _select_limit(request)
        if limit is None:
            return await call_next(request)

        key = get_user_key(request)

        # Allowed team members are exempt from rate limiting
        global _EXEMPT_IDS
        if not _EXEMPT_IDS:
            _EXEMPT_IDS = _build_exempt_ids()
        if key in _EXEMPT_IDS:
            return await call_next(request)

        # Namespace by limit tier to keep counters separate
        namespace = f"rl:{limit.amount}/{limit.multiples}"

        if not _limiter.hit(limit, namespace, key):
            window = limit.get_expiry()
            logger.info(
                "Rate limit exceeded: user=%s path=%s limit=%s",
                key, request.url.path, str(limit),
            )
            return _make_429_response(retry_after=window)

        return await call_next(request)


# ---------------------------------------------------------------------------
# For tests: reset all counters
# ---------------------------------------------------------------------------

def reset_limits() -> None:
    """Clear all rate limit counters (for testing)."""
    _storage.reset()
