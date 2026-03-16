"""Async CRUD for TrackedThreadModel — stores brand-relevant Threads conversations."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select, update, func

from db.session import AsyncSessionLocal
from db.models import TrackedThreadModel

logger = logging.getLogger(__name__)


async def is_already_tracked(thread_id: str) -> bool:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(TrackedThreadModel.id).filter(TrackedThreadModel.thread_id == thread_id)
        )
        return result.scalar_one_or_none() is not None


async def save_tracked_thread(
    thread_id: str,
    *,
    platform: str = "threads",
    source: str = "mention",
    author_username: str = "",
    text: str = "",
    permalink: str = "",
    root_text: str = "",
    keyword_matched: str = "",
    like_count: int = 0,
    reply_count: int = 0,
) -> TrackedThreadModel:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(TrackedThreadModel).filter(TrackedThreadModel.thread_id == thread_id)
        )
        existing = result.scalar_one_or_none()
        if existing:
            return existing

        m = TrackedThreadModel(
            thread_id=thread_id,
            platform=platform,
            source=source,
            author_username=author_username,
            text=text[:4000],
            permalink=permalink,
            root_text=root_text[:4000],
            keyword_matched=keyword_matched,
            like_count=like_count,
            reply_count=reply_count,
            status="new",
            found_at=datetime.now(timezone.utc),
        )
        session.add(m)
        await session.commit()
        await session.refresh(m)
        return m


async def list_tracked_threads(
    *,
    status: str | None = None,
    min_score: float = 0.0,
    limit: int = 20,
) -> list[TrackedThreadModel]:
    async with AsyncSessionLocal() as session:
        q = (
            select(TrackedThreadModel)
            .order_by(
                TrackedThreadModel.relevance_score.desc(),
                TrackedThreadModel.found_at.desc(),
            )
            .limit(limit)
        )
        if status:
            q = q.filter(TrackedThreadModel.status == status)
        if min_score > 0:
            q = q.filter(TrackedThreadModel.relevance_score >= min_score)
        result = await session.execute(q)
        return list(result.scalars().all())


async def get_tracked_thread(thread_id: str) -> TrackedThreadModel | None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(TrackedThreadModel).filter(TrackedThreadModel.thread_id == thread_id)
        )
        return result.scalar_one_or_none()


async def update_tracked_status(thread_id: str, status: str) -> None:
    async with AsyncSessionLocal() as session:
        values: dict = {"status": status}
        if status in ("replied", "content_created"):
            values["acted_at"] = datetime.now(timezone.utc)
        await session.execute(
            update(TrackedThreadModel)
            .filter(TrackedThreadModel.thread_id == thread_id)
            .values(**values)
        )
        await session.commit()


async def update_thread_scoring(
    thread_id: str,
    *,
    relevance_score: float = 0.0,
    relevance_reason: str = "",
    suggested_action: str = "",
    ai_summary: str = "",
    content_angle: str = "",
    topic_tags: list[str] | None = None,
) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(TrackedThreadModel)
            .filter(TrackedThreadModel.thread_id == thread_id)
            .values(
                relevance_score=relevance_score,
                relevance_reason=relevance_reason,
                suggested_action=suggested_action,
                ai_summary=ai_summary,
                content_angle=content_angle,
                topic_tags=topic_tags or [],
            )
        )
        await session.commit()


async def count_by_status() -> dict[str, int]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(TrackedThreadModel.status, func.count(TrackedThreadModel.id))
            .group_by(TrackedThreadModel.status)
        )
        return dict(result.all())
