"""CRUD helpers for TrendSignal and CollectorHealth persistence."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from analytics.base import TrendItem
from db.models import CollectorHealth, TrendSignal
from db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)


async def save_signals(source_key: str, items: list[TrendItem]) -> None:
    """Persist raw collection results as TrendSignal rows."""
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        for item in items:
            sig = TrendSignal(
                source_key=source_key,
                collected_at=now,
                keyword=item.title,
                score_raw=_parse_score(item.score),
                items_json={
                    "url": item.url,
                    "score": item.score,
                    "extra": item.extra,
                    "summary": item.summary,
                },
            )
            session.add(sig)
        await session.commit()


async def get_cached_signals(source_key: str, max_age_hours: int = 24) -> list[TrendSignal]:
    """Return the most recent batch of signals for *source_key* within *max_age_hours*."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    async with AsyncSessionLocal() as session:
        # Find the latest collected_at for this source within the age window
        latest_q = (
            select(TrendSignal.collected_at)
            .where(TrendSignal.source_key == source_key, TrendSignal.collected_at >= cutoff)
            .order_by(TrendSignal.collected_at.desc())
            .limit(1)
        )
        latest_row = (await session.execute(latest_q)).scalar_one_or_none()
        if latest_row is None:
            return []
        rows = (
            await session.execute(
                select(TrendSignal).where(
                    TrendSignal.source_key == source_key,
                    TrendSignal.collected_at == latest_row,
                )
            )
        ).scalars().all()
        return list(rows)


async def update_health(source_key: str, success: bool, error: str = "") -> None:
    """Upsert collector health record."""
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        row = (
            await session.execute(
                select(CollectorHealth).where(CollectorHealth.source_key == source_key)
            )
        ).scalar_one_or_none()
        if row is None:
            row = CollectorHealth(source_key=source_key)
            session.add(row)
        if success:
            row.last_success = now
            row.consecutive_failures = 0
            row.circuit_open_until = None
            row.last_error = ""
        else:
            row.last_failure = now
            row.consecutive_failures = (row.consecutive_failures or 0) + 1
            row.last_error = error[:1000]
        await session.commit()


async def set_circuit_open_until(source_key: str, until: datetime) -> None:
    """Set the circuit breaker open-until timestamp."""
    async with AsyncSessionLocal() as session:
        row = (
            await session.execute(
                select(CollectorHealth).where(CollectorHealth.source_key == source_key)
            )
        ).scalar_one_or_none()
        if row is not None:
            row.circuit_open_until = until
            await session.commit()


async def get_health_status() -> list[dict]:
    """Return health status for all known collectors."""
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(select(CollectorHealth))).scalars().all()
        return [
            {
                "source_key": r.source_key,
                "last_success": r.last_success.isoformat() if r.last_success else None,
                "last_failure": r.last_failure.isoformat() if r.last_failure else None,
                "consecutive_failures": r.consecutive_failures,
                "circuit_open_until": r.circuit_open_until.isoformat() if r.circuit_open_until else None,
                "last_error": r.last_error,
            }
            for r in rows
        ]


async def get_health_row(source_key: str) -> CollectorHealth | None:
    """Return the health row for a single collector."""
    async with AsyncSessionLocal() as session:
        return (
            await session.execute(
                select(CollectorHealth).where(CollectorHealth.source_key == source_key)
            )
        ).scalar_one_or_none()


def _parse_score(score_str: str) -> float:
    """Best-effort parse a score string to float."""
    if not score_str:
        return 0.0
    cleaned = "".join(c for c in score_str if c.isdigit() or c in ".,-")
    cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return 0.0
