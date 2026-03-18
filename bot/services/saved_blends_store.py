"""CRUD for user-saved blends (SavedBlendModel)."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import or_, select

from db.models import SavedBlendModel
from db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)


def _row_to_dict(m: SavedBlendModel) -> dict[str, Any]:
    return {
        "id": m.saved_id,
        "telegram_id": m.telegram_id,
        "title": m.title,
        "brief": m.brief,
        "tags": m.tags or [],
        "oils": m.oils or [],
        "total_drops": m.total_drops,
        "profile": m.profile or {},
        "expert_note": m.expert_note,
        "application_guide": m.application_guide,
        "safety_status": m.safety_status,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


async def save_blend(
    *,
    telegram_id: int,
    title: str,
    brief: str = "",
    tags: list | None = None,
    oils: list | None = None,
    total_drops: int = 0,
    profile: dict | None = None,
    expert_note: str = "",
    application_guide: str = "",
    safety_status: str = "safe",
    team_id: str | None = None,
) -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        m = SavedBlendModel(
            saved_id=str(uuid.uuid4()),
            telegram_id=telegram_id,
            title=title,
            brief=brief,
            tags=tags or [],
            oils=oils or [],
            total_drops=total_drops,
            profile=profile or {},
            expert_note=expert_note,
            application_guide=application_guide,
            safety_status=safety_status,
        )
        if team_id is not None:
            m.team_id = team_id
        session.add(m)
        await session.commit()
        await session.refresh(m)
        return _row_to_dict(m)


async def list_saved_blends(telegram_id: int, *, team_id: str | None = None) -> list[dict[str, Any]]:
    async with AsyncSessionLocal() as session:
        query = (
            select(SavedBlendModel)
            .filter(SavedBlendModel.telegram_id == telegram_id)
            .order_by(SavedBlendModel.created_at.desc())
        )
        if team_id is not None:
            query = query.filter(or_(SavedBlendModel.team_id == team_id, SavedBlendModel.team_id.is_(None)))
        result = await session.execute(query)
        return [_row_to_dict(m) for m in result.scalars().all()]


async def delete_saved_blend(telegram_id: int, saved_id: str) -> bool:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(SavedBlendModel).filter(
                SavedBlendModel.saved_id == saved_id,
                SavedBlendModel.telegram_id == telegram_id,
            )
        )
        m = result.scalar_one_or_none()
        if m is None:
            return False
        await session.delete(m)
        await session.commit()
        return True


async def get_blend_by_id(saved_id: str) -> dict[str, Any] | None:
    """Fetch a single saved blend by saved_id (no telegram_id filter)."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(SavedBlendModel).filter(SavedBlendModel.saved_id == saved_id)
        )
        m = result.scalar_one_or_none()
        return _row_to_dict(m) if m else None
