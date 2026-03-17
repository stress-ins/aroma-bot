"""LLM response cache — avoids redundant API calls for identical requests."""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from db.models import LlmCacheModel
from db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)


def make_cache_key(cache_type: str, **params: str) -> str:
    """Build a deterministic SHA-256 cache key from type + sorted params."""
    parts = [cache_type]
    for k in sorted(params):
        parts.append(f"{k}={params[k]}")
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode()).hexdigest()


async def get_cached(cache_key: str) -> dict | None:
    """Return cached result if exists and not expired, else None."""
    async with AsyncSessionLocal() as session:
        row = (
            await session.execute(
                select(LlmCacheModel).where(LlmCacheModel.cache_key == cache_key)
            )
        ).scalar_one_or_none()
        if not row:
            return None
        expires = row.expires_at.replace(tzinfo=timezone.utc) if row.expires_at.tzinfo is None else row.expires_at
        if expires < datetime.now(timezone.utc):
            await session.delete(row)
            await session.commit()
            return None
        row.hit_count += 1
        await session.commit()
        logger.debug("LLM cache hit: %s (hits=%d)", cache_key[:16], row.hit_count)
        return dict(row.result)


async def set_cached(
    cache_key: str,
    cache_type: str,
    result: dict,
    ttl_hours: int,
    telegram_id: int | None = None,
) -> None:
    """Store an LLM result in cache."""
    async with AsyncSessionLocal() as session:
        existing = (
            await session.execute(
                select(LlmCacheModel).where(LlmCacheModel.cache_key == cache_key)
            )
        ).scalar_one_or_none()
        now = datetime.now(timezone.utc)
        expires = now + timedelta(hours=ttl_hours)
        if existing:
            existing.result = result
            existing.expires_at = expires
            existing.hit_count = 0
            existing.created_at = now
        else:
            session.add(
                LlmCacheModel(
                    cache_key=cache_key,
                    cache_type=cache_type,
                    telegram_id=telegram_id,
                    result=result,
                    expires_at=expires,
                )
            )
        await session.commit()
