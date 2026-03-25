"""Usage analytics event store — insert and aggregate lightweight product events."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select, cast, String

from db.models import AnalyticsEvent
from db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)


async def log_event(
    *,
    team_id: str | None = None,
    telegram_id: int | None = None,
    event_name: str,
    category: str = "",
    data: dict[str, Any] | None = None,
    session_id: str = "",
) -> AnalyticsEvent:
    """Insert a single analytics event."""
    async with AsyncSessionLocal() as session:
        event = AnalyticsEvent(
            team_id=team_id,
            telegram_id=telegram_id,
            event_name=event_name,
            event_category=category,
            event_data=data or {},
            session_id=session_id,
        )
        session.add(event)
        await session.commit()
        await session.refresh(event)
        return event


async def log_events_batch(
    events: list[dict[str, Any]],
    *,
    team_id: str | None = None,
    telegram_id: int | None = None,
) -> int:
    """Insert a batch of analytics events. Returns count inserted."""
    if not events:
        return 0
    async with AsyncSessionLocal() as session:
        for ev in events:
            session.add(AnalyticsEvent(
                team_id=team_id,
                telegram_id=telegram_id,
                event_name=ev.get("event_name", "unknown"),
                event_category=ev.get("category", ""),
                event_data=ev.get("data") or {},
                session_id=ev.get("session_id", ""),
            ))
        await session.commit()
    return len(events)


async def get_event_counts(
    team_id: str | None = None,
    since: datetime | None = None,
    event_name: str | None = None,
) -> int:
    """Count events, optionally filtered by team, time range, and event name."""
    async with AsyncSessionLocal() as session:
        q = select(func.count(AnalyticsEvent.id))
        if team_id is not None:
            q = q.where(AnalyticsEvent.team_id == team_id)
        if since is not None:
            q = q.where(AnalyticsEvent.created_at >= since)
        if event_name is not None:
            q = q.where(AnalyticsEvent.event_name == event_name)
        result = await session.execute(q)
        return result.scalar() or 0


async def get_daily_active_users(
    team_id: str | None = None,
    since: datetime | None = None,
) -> list[dict[str, Any]]:
    """Unique telegram_ids per day since given date."""
    async with AsyncSessionLocal() as session:
        date_col = func.date(AnalyticsEvent.created_at)
        q = (
            select(
                date_col.label("date"),
                func.count(func.distinct(AnalyticsEvent.telegram_id)).label("count"),
            )
            .where(AnalyticsEvent.telegram_id.isnot(None))
            .group_by(date_col)
            .order_by(date_col)
        )
        if team_id is not None:
            q = q.where(AnalyticsEvent.team_id == team_id)
        if since is not None:
            q = q.where(AnalyticsEvent.created_at >= since)
        result = await session.execute(q)
        return [{"date": str(row.date), "count": row.count} for row in result.all()]


async def get_popular_events(
    team_id: str | None = None,
    since: datetime | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Top events by count."""
    async with AsyncSessionLocal() as session:
        q = (
            select(
                AnalyticsEvent.event_name,
                func.count(AnalyticsEvent.id).label("count"),
            )
            .group_by(AnalyticsEvent.event_name)
            .order_by(func.count(AnalyticsEvent.id).desc())
            .limit(limit)
        )
        if team_id is not None:
            q = q.where(AnalyticsEvent.team_id == team_id)
        if since is not None:
            q = q.where(AnalyticsEvent.created_at >= since)
        result = await session.execute(q)
        return [{"event_name": row.event_name, "count": row.count} for row in result.all()]


async def get_feature_usage(
    team_id: str | None = None,
    since: datetime | None = None,
) -> dict[str, int]:
    """Event counts grouped by category."""
    async with AsyncSessionLocal() as session:
        q = (
            select(
                AnalyticsEvent.event_category,
                func.count(AnalyticsEvent.id).label("count"),
            )
            .group_by(AnalyticsEvent.event_category)
        )
        if team_id is not None:
            q = q.where(AnalyticsEvent.team_id == team_id)
        if since is not None:
            q = q.where(AnalyticsEvent.created_at >= since)
        result = await session.execute(q)
        return {row.event_category or "other": row.count for row in result.all()}
