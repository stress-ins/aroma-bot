"""Async CRUD for PostMetricsModel — stores engagement metric snapshots."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, func

from db.session import AsyncSessionLocal
from db.models import PostMetricsModel, DraftModel

logger = logging.getLogger(__name__)


def _serialize(m: PostMetricsModel) -> dict[str, Any]:
    return {
        "id": m.id,
        "draft_id": m.draft_id,
        "platform": m.platform,
        "external_id": m.external_id,
        "metrics": dict(m.metrics) if m.metrics else {},
        "fetched_at": m.fetched_at.isoformat() if isinstance(m.fetched_at, datetime) else str(m.fetched_at),
    }


async def save_metrics(
    draft_id: str,
    platform: str,
    external_id: str,
    metrics: dict[str, Any],
    *,
    team_id: str | None = None,
) -> int:
    """Save a metrics snapshot. Returns the row id."""
    async with AsyncSessionLocal() as session:
        model = PostMetricsModel(
            draft_id=draft_id,
            platform=platform,
            external_id=external_id,
            metrics=metrics,
            fetched_at=datetime.now(timezone.utc),
        )
        if team_id is not None:
            model.team_id = team_id
        session.add(model)
        await session.commit()
        await session.refresh(model)
        return model.id


async def get_latest_metrics(draft_id: str) -> list[dict[str, Any]]:
    """Return the latest snapshot per platform for a given draft."""
    async with AsyncSessionLocal() as session:
        # Subquery: max fetched_at per platform
        sub = (
            select(
                PostMetricsModel.platform,
                func.max(PostMetricsModel.fetched_at).label("max_fetched"),
            )
            .filter(PostMetricsModel.draft_id == draft_id)
            .group_by(PostMetricsModel.platform)
            .subquery()
        )
        query = (
            select(PostMetricsModel)
            .join(
                sub,
                (PostMetricsModel.platform == sub.c.platform)
                & (PostMetricsModel.fetched_at == sub.c.max_fetched)
                & (PostMetricsModel.draft_id == draft_id),
            )
        )
        result = await session.execute(query)
        return [_serialize(m) for m in result.scalars().all()]


async def get_latest_metrics_batch(draft_ids: list[str]) -> dict[str, dict[str, Any]]:
    """Return the latest metrics snapshot per draft, aggregated across platforms.

    Returns a dict keyed by draft_id with a summary: {likes, views, replies, comments}.
    Only includes drafts that have metrics.
    """
    if not draft_ids:
        return {}

    async with AsyncSessionLocal() as session:
        # Subquery: max fetched_at per (draft_id, platform)
        sub = (
            select(
                PostMetricsModel.draft_id,
                PostMetricsModel.platform,
                func.max(PostMetricsModel.fetched_at).label("max_fetched"),
            )
            .filter(PostMetricsModel.draft_id.in_(draft_ids))
            .group_by(PostMetricsModel.draft_id, PostMetricsModel.platform)
            .subquery()
        )
        query = (
            select(PostMetricsModel)
            .join(
                sub,
                (PostMetricsModel.draft_id == sub.c.draft_id)
                & (PostMetricsModel.platform == sub.c.platform)
                & (PostMetricsModel.fetched_at == sub.c.max_fetched),
            )
        )
        result = await session.execute(query)
        rows = result.scalars().all()

    # Aggregate per draft_id
    batch: dict[str, dict[str, Any]] = {}
    for m in rows:
        metrics = dict(m.metrics) if m.metrics else {}
        if m.draft_id not in batch:
            batch[m.draft_id] = {"likes": 0, "views": 0, "replies": 0, "comments": 0}
        summary = batch[m.draft_id]
        summary["likes"] += int(metrics.get("likes", 0) or 0)
        summary["views"] += int(metrics.get("views", 0) or metrics.get("impressions", 0) or 0)
        summary["replies"] += int(metrics.get("replies", 0) or 0)
        summary["comments"] += int(metrics.get("comments", 0) or 0)

    return batch


async def get_metrics_history(draft_id: str, platform: str) -> list[dict[str, Any]]:
    """Return all snapshots for a draft+platform, newest first."""
    async with AsyncSessionLocal() as session:
        query = (
            select(PostMetricsModel)
            .filter(
                PostMetricsModel.draft_id == draft_id,
                PostMetricsModel.platform == platform,
            )
            .order_by(PostMetricsModel.fetched_at.desc())
        )
        result = await session.execute(query)
        return [_serialize(m) for m in result.scalars().all()]


async def list_drafts_needing_fetch(
    max_age_days: int = 7,
    min_interval_hours: int = 6,
) -> list[dict[str, Any]]:
    """Find published drafts that need a fresh metrics fetch.

    Criteria:
    - status == "published"
    - external_ids is not empty (JSON dict with at least one key)
    - published_at within last `max_age_days`
    - last fetch was >min_interval_hours ago, or no fetch exists
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    interval_cutoff = datetime.now(timezone.utc) - timedelta(hours=min_interval_hours)

    async with AsyncSessionLocal() as session:
        # Get published drafts with external_ids
        query = (
            select(DraftModel)
            .filter(
                DraftModel.status == "published",
                DraftModel.published_at >= cutoff,
            )
        )
        result = await session.execute(query)
        drafts = result.scalars().all()

        needs_fetch = []
        for d in drafts:
            ext = d.external_ids
            if not ext or not isinstance(ext, dict) or not any(ext.values()):
                continue

            # Check last fetch time
            last_fetch_q = (
                select(func.max(PostMetricsModel.fetched_at))
                .filter(PostMetricsModel.draft_id == d.draft_id)
            )
            last_result = await session.execute(last_fetch_q)
            last_fetched = last_result.scalar()

            if last_fetched and last_fetched > interval_cutoff:
                continue  # Too recent

            needs_fetch.append({
                "draft_id": d.draft_id,
                "external_ids": dict(ext),
                "published_at": d.published_at.isoformat() if d.published_at else None,
            })

        return needs_fetch
