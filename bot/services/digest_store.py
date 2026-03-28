"""Digest cache store — persist/read digest reports in DB."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from db.models.analytics import DigestCache
from db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)

_DIGEST_KEY = "daily_digest"


async def save_digest(ru_report: str, en_report: str) -> None:
    """Save digest reports to DB (upsert by key)."""
    async with AsyncSessionLocal() as session:
        row = (
            await session.execute(
                select(DigestCache).where(DigestCache.cache_key == _DIGEST_KEY)
            )
        ).scalar_one_or_none()

        now = datetime.now(timezone.utc)
        value = {
            "ru_report": ru_report,
            "en_report": en_report,
            "generated_at": now.isoformat(),
        }

        if row:
            row.value_json = value
            row.updated_at = now
        else:
            row = DigestCache(
                cache_key=_DIGEST_KEY,
                value_json=value,
                updated_at=now,
            )
            session.add(row)

        await session.commit()
        logger.info("Digest saved to DB at %s", now.isoformat())


async def get_digest() -> dict[str, Any] | None:
    """Read the latest digest from DB. Returns dict with ru_report, en_report, generated_at or None."""
    async with AsyncSessionLocal() as session:
        row = (
            await session.execute(
                select(DigestCache).where(DigestCache.cache_key == _DIGEST_KEY)
            )
        ).scalar_one_or_none()

        if not row or not row.value_json:
            return None
        return dict(row.value_json)
