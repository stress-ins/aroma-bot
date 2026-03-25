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


# ── Content Analytics Dashboard ───────────────────────────────────────────────


@router.get("/api/analytics/dashboard")
async def analytics_dashboard(
    ctx: TeamContext = Depends(_resolve_team_context),
    days: int = Query(default=30, ge=7, le=90),
):
    """Content performance dashboard — format/pillar/time analytics."""
    import asyncio

    from sqlalchemy import func, select, extract

    from db.models import PastPublicationModel
    from db.session import AsyncSessionLocal

    since = datetime.now(timezone.utc) - timedelta(days=days)
    team_id = ctx.team_id

    # Gather format, pillar, and top posts concurrently
    from bot.services.content_analytics import (
        get_format_performance,
        get_pillar_performance,
        get_top_publications,
    )

    format_perf, pillar_perf, top_posts = await asyncio.gather(
        get_format_performance(team_id),
        get_pillar_performance(team_id),
        get_top_publications(team_id, limit=5),
    )

    # Time performance: best day of week and hour from published_at
    M = PastPublicationModel
    async with AsyncSessionLocal() as session:
        # Total published count
        count_q = select(func.count()).select_from(M)
        if team_id:
            count_q = count_q.filter(M.team_id == team_id)
        count_q = count_q.filter(M.published_at >= since)
        total_result = await session.execute(count_q)
        total_published = total_result.scalar() or 0

        # Day-of-week performance
        dow_q = (
            select(
                extract("dow", M.published_at).label("dow"),
                func.count().label("cnt"),
                func.avg(M.score_engagement).label("avg_eng"),
            )
            .filter(M.published_at.isnot(None), M.score_engagement.isnot(None))
            .group_by(extract("dow", M.published_at))
        )
        if team_id:
            dow_q = dow_q.filter(M.team_id == team_id)
        dow_result = await session.execute(dow_q)
        dow_rows = dow_result.all()

        # Hour-of-day performance
        hour_q = (
            select(
                extract("hour", M.published_at).label("hour"),
                func.count().label("cnt"),
                func.avg(M.score_engagement).label("avg_eng"),
            )
            .filter(M.published_at.isnot(None), M.score_engagement.isnot(None))
            .group_by(extract("hour", M.published_at))
        )
        if team_id:
            hour_q = hour_q.filter(M.team_id == team_id)
        hour_result = await session.execute(hour_q)
        hour_rows = hour_result.all()

    DAY_NAMES = ["Вс", "Пн", "Вт", "Ср", "Чт", "Пт", "Сб"]

    best_day = None
    if dow_rows:
        best = max(dow_rows, key=lambda r: float(r.avg_eng or 0))
        idx = int(best.dow) if best.dow is not None else 0
        best_day = {"day": DAY_NAMES[idx % 7], "day_index": idx, "avg_engagement": round(float(best.avg_eng or 0), 1), "count": best.cnt}

    best_hour = None
    if hour_rows:
        best = max(hour_rows, key=lambda r: float(r.avg_eng or 0))
        h = int(best.hour) if best.hour is not None else 0
        best_hour = {"hour": h, "label": f"{h:02d}:00", "avg_engagement": round(float(best.avg_eng or 0), 1), "count": best.cnt}

    return {
        "period_days": days,
        "total_published": total_published,
        "format_performance": format_perf,
        "pillar_performance": pillar_perf,
        "time_performance": {
            "best_day": best_day,
            "best_hour": best_hour,
        },
        "top_posts": top_posts,
    }


@router.get("/api/analytics/recommendations")
async def analytics_recommendations(
    ctx: TeamContext = Depends(_resolve_team_context),
):
    """Generate actionable content recommendations based on past performance."""
    from bot.services.content_analytics import (
        get_format_performance,
        get_pillar_performance,
    )

    team_id = ctx.team_id
    formats = await get_format_performance(team_id)
    pillars = await get_pillar_performance(team_id)

    KIND_LABELS: dict[str, str] = {
        "carousel": "Карусели",
        "reels": "Рилсы",
        "text": "Текстовые посты",
        "stories": "Сторис",
        "image": "Фото-посты",
        "threads_series": "Серии в Threads",
        "content": "Контент",
    }

    best_format = max(formats, key=lambda f: f["avg_score"]) if formats else None
    best_pillar = max(pillars, key=lambda p: p["avg_score"]) if pillars else None

    suggestions: list[str] = []

    if best_format and len(formats) > 1:
        worst = min(formats, key=lambda f: f["avg_score"])
        if worst["avg_score"] > 0:
            diff = round((best_format["avg_score"] / worst["avg_score"] - 1) * 100)
            if diff > 10:
                best_label = KIND_LABELS.get(best_format["kind"], best_format["kind"])
                worst_label = KIND_LABELS.get(worst["kind"], worst["kind"])
                suggestions.append(
                    f"{best_label} получают на {diff}% больше вовлечения, чем {worst_label.lower()}. "
                    f"Рассмотрите увеличение доли {best_label.lower()} в контент-плане."
                )

    if best_pillar and len(pillars) > 1:
        low_pillars = [p for p in pillars if p["avg_score"] < best_pillar["avg_score"] * 0.7]
        if low_pillars:
            names = ", ".join(p["pillar"] for p in low_pillars[:2])
            suggestions.append(
                f"Столпы «{names}» показывают низкую вовлечённость. "
                f"Попробуйте обновить подход или объединить с темой «{best_pillar['pillar']}»."
            )

    if best_format and best_format["count"] < 3:
        best_label = KIND_LABELS.get(best_format["kind"], best_format["kind"])
        suggestions.append(
            f"{best_label} показывают высокий потенциал, но выборка мала ({best_format['count']} публ.). "
            f"Опубликуйте ещё 3-5 для надёжной статистики."
        )

    if formats:
        total = sum(f["count"] for f in formats)
        for f in formats:
            share = f["count"] / total if total else 0
            if share > 0.6:
                label = KIND_LABELS.get(f["kind"], f["kind"])
                suggestions.append(
                    f"{label} составляют {round(share * 100)}% публикаций. "
                    f"Диверсифицируйте форматы для охвата разных сегментов аудитории."
                )

    if not formats and not pillars:
        suggestions.append("Пока нет данных для анализа. Опубликуйте контент и оцените его в Архиве.")

    if not suggestions:
        suggestions.append("Продолжайте в том же духе! Результаты стабильные.")

    return {
        "best_format": best_format,
        "best_pillar": best_pillar,
        "suggestions": suggestions[:5],
    }
