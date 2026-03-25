"""Analytics API — log usage events and retrieve aggregated stats."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from miniapp.api.auth import _resolve_team_context, TeamContext
from miniapp.api.routers.admin import _require_admin
from bot.services.analytics_store import (
    get_daily_active_users,
    get_event_counts,
    get_feature_usage,
    get_popular_events,
    log_events_batch,
)

logger = logging.getLogger(__name__)
router = APIRouter()


class EventPayload(BaseModel):
    event_name: str = Field(max_length=64)
    category: str = Field(default="", max_length=32)
    data: dict[str, Any] = Field(default_factory=dict)
    session_id: str = Field(default="", max_length=36)


class BatchEventPayload(BaseModel):
    events: list[EventPayload] = Field(max_length=50)


@router.post("/api/analytics/event")
async def log_analytics_event(
    body: BatchEventPayload,
    ctx: TeamContext = Depends(_resolve_team_context),
):
    """Log a batch of analytics events from the frontend tracker."""
    count = await log_events_batch(
        [ev.model_dump() for ev in body.events],
        team_id=ctx.team_id,
        telegram_id=ctx.telegram_id,
    )
    return {"ok": True, "count": count}


@router.get("/api/analytics/summary")
async def analytics_summary(
    admin_id: int = Depends(_require_admin),
    days: int = Query(default=7, ge=1, le=90),
):
    """Aggregated analytics summary for admin dashboard."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    total, dau, top_events, feature = await _gather_summary(since)
    return {
        f"total_events_{days}d": total,
        f"daily_active_users_{days}d": dau,
        f"top_events_{days}d": top_events,
        f"feature_usage_{days}d": feature,
    }


@router.get("/api/analytics/events")
async def analytics_events_list(
    admin_id: int = Depends(_require_admin),
    days: int = Query(default=7, ge=1, le=90),
    event_name: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """Recent events list with pagination (admin only)."""
    from sqlalchemy import select

    from db.models import AnalyticsEvent
    from db.session import AsyncSessionLocal

    since = datetime.now(timezone.utc) - timedelta(days=days)
    async with AsyncSessionLocal() as session:
        q = (
            select(AnalyticsEvent)
            .where(AnalyticsEvent.created_at >= since)
            .order_by(AnalyticsEvent.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        if event_name:
            q = q.where(AnalyticsEvent.event_name == event_name)
        result = await session.execute(q)
        rows = result.scalars().all()

    return {
        "events": [
            {
                "id": r.id,
                "team_id": r.team_id,
                "telegram_id": r.telegram_id,
                "event_name": r.event_name,
                "event_category": r.event_category,
                "event_data": r.event_data,
                "session_id": r.session_id,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
        "offset": offset,
        "limit": limit,
    }


async def _gather_summary(since: datetime):
    """Gather all summary data concurrently."""
    import asyncio

    total, dau, top_events, feature = await asyncio.gather(
        get_event_counts(since=since),
        get_daily_active_users(since=since),
        get_popular_events(since=since, limit=20),
        get_feature_usage(since=since),
    )
    return total, dau, top_events, feature
