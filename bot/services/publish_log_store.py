"""Async CRUD for PublishLogModel — tracks every publish/schedule attempt."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import or_, select, update

from db.session import AsyncSessionLocal
from db.models import PublishLogModel

logger = logging.getLogger(__name__)


async def save_log(
    draft_id: str,
    platform: str,
    action: str,
    status: str,
    *,
    external_id: str = "",
    error_message: str = "",
    attempt_num: int = 1,
) -> int:
    """Create a publish log entry. Returns the log row id."""
    async with AsyncSessionLocal() as session:
        model = PublishLogModel(
            draft_id=draft_id,
            platform=platform,
            action=action,
            status=status,
            external_id=external_id,
            error_message=error_message,
            attempt_num=attempt_num,
            created_at=datetime.now(timezone.utc),
        )
        session.add(model)
        await session.commit()
        await session.refresh(model)
        return model.id


async def list_logs(draft_id: str) -> list[dict[str, Any]]:
    """Return all publish log entries for a draft, newest first."""
    async with AsyncSessionLocal() as session:
        query = (
            select(PublishLogModel)
            .filter(PublishLogModel.draft_id == draft_id)
            .order_by(PublishLogModel.created_at.desc())
        )
        result = await session.execute(query)
        models = result.scalars().all()
        return [
            {
                "id": m.id,
                "draft_id": m.draft_id,
                "platform": m.platform,
                "action": m.action,
                "status": m.status,
                "external_id": m.external_id,
                "error_message": m.error_message,
                "attempt_num": m.attempt_num,
                "created_at": m.created_at.isoformat() if isinstance(m.created_at, datetime) else str(m.created_at),
            }
            for m in models
        ]


async def update_log_status(
    log_id: int,
    status: str,
    *,
    external_id: str | None = None,
    error_message: str | None = None,
) -> None:
    """Update status (and optionally external_id/error) of a log entry."""
    async with AsyncSessionLocal() as session:
        values: dict[str, Any] = {"status": status}
        if external_id is not None:
            values["external_id"] = external_id
        if error_message is not None:
            values["error_message"] = error_message
        await session.execute(
            update(PublishLogModel).where(PublishLogModel.id == log_id).values(**values)
        )
        await session.commit()


async def list_all_logs(limit: int = 50, *, team_id: str | None = None) -> list[dict[str, Any]]:
    """Return the most recent publish log entries across all drafts."""
    async with AsyncSessionLocal() as session:
        query = select(PublishLogModel).order_by(PublishLogModel.created_at.desc())
        if team_id is not None:
            query = query.filter(or_(PublishLogModel.team_id == team_id, PublishLogModel.team_id.is_(None)))
        query = query.limit(limit)
        result = await session.execute(query)
        models = result.scalars().all()
        return [
            {
                "id": m.id,
                "draft_id": m.draft_id,
                "platform": m.platform,
                "action": m.action,
                "status": m.status,
                "external_id": m.external_id,
                "error_message": m.error_message,
                "attempt_num": m.attempt_num,
                "created_at": m.created_at.isoformat() if isinstance(m.created_at, datetime) else str(m.created_at),
            }
            for m in models
        ]
