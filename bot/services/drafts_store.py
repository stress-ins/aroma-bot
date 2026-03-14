from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select, update, delete
from sqlalchemy.orm import selectinload

from db.session import AsyncSessionLocal
from db.models import DraftModel

logger = logging.getLogger(__name__)


class DraftRecord:
    def __init__(
        self,
        draft_id: str,
        kind: str,
        topic: str,
        source: str,
        created_at: str,
        status: str,
        feedback: str,
        payload: dict[str, Any],
        seq_id: int | None = None,
        scheduled_at: str | None = None,
        publish_platforms: list[str] | None = None,
        external_ids: dict[str, Any] | None = None,
    ):
        self.draft_id = draft_id
        self.kind = kind
        self.topic = topic
        self.source = source
        self.created_at = created_at
        self.status = status
        self.feedback = feedback
        self.payload = payload
        self.seq_id = seq_id
        self.scheduled_at = scheduled_at
        self.publish_platforms = publish_platforms or []
        self.external_ids = external_ids or {}

    @classmethod
    def from_model(cls, model: DraftModel) -> DraftRecord:
        scheduled_at = None
        if model.scheduled_at:
            scheduled_at = model.scheduled_at.isoformat() if isinstance(model.scheduled_at, datetime) else str(model.scheduled_at)
        return cls(
            draft_id=model.draft_id,
            kind=model.kind,
            topic=model.topic,
            source=model.source,
            created_at=model.created_at.isoformat() if isinstance(model.created_at, datetime) else str(model.created_at),
            status=model.status,
            feedback=model.feedback,
            payload=model.payload,
            seq_id=model.id,
            scheduled_at=scheduled_at,
            publish_platforms=model.publish_platforms or [],
            external_ids=model.external_ids or {},
        )


async def save_draft(kind: str, topic: str, source: str, payload: dict[str, Any]) -> DraftRecord:
    draft_id = uuid4().hex[:8]
    created_at = datetime.now(timezone.utc)
    
    async with AsyncSessionLocal() as session:
        model = DraftModel(
            draft_id=draft_id,
            kind=kind,
            topic=topic.strip(),
            source=source.strip(),
            status="draft",
            feedback="",
            payload=payload,
            created_at=created_at,
        )
        session.add(model)
        await session.commit()
        await session.refresh(model)
        return DraftRecord.from_model(model)


async def list_recent_drafts(
    limit: int = 10,
    kind: str | None = None,
    newest_first: bool = False,
) -> list[DraftRecord]:
    async with AsyncSessionLocal() as session:
        order = DraftModel.id.desc() if newest_first else DraftModel.id.asc()
        query = select(DraftModel).order_by(order)
        if kind:
            query = query.filter(DraftModel.kind == kind)
        query = query.limit(limit)
        result = await session.execute(query)
        models = result.scalars().all()
        return [DraftRecord.from_model(m) for m in models]


async def get_draft(draft_id: str) -> DraftRecord | None:
    async with AsyncSessionLocal() as session:
        query = select(DraftModel).filter(DraftModel.draft_id == draft_id)
        result = await session.execute(query)
        model = result.scalar_one_or_none()
        if model:
            return DraftRecord.from_model(model)
        return None


_SENTINEL = object()


async def update_draft(
    draft_id: str,
    *,
    topic: str | None = None,
    status: str | None = None,
    feedback: str | None = None,
    payload: dict[str, Any] | None = None,
    scheduled_at: Any = _SENTINEL,
    publish_platforms: list[str] | None = None,
    external_ids: dict[str, Any] | None = None,
) -> DraftRecord | None:
    async with AsyncSessionLocal() as session:
        query = select(DraftModel).filter(DraftModel.draft_id == draft_id)
        result = await session.execute(query)
        model = result.scalar_one_or_none()

        if not model:
            return None

        if topic is not None:
            model.topic = topic
        if status is not None:
            model.status = status
        if feedback is not None:
            model.feedback = feedback
        if payload is not None:
            model.payload = dict(payload)
        if scheduled_at is not _SENTINEL:
            model.scheduled_at = scheduled_at
        if publish_platforms is not None:
            model.publish_platforms = list(publish_platforms)
        if external_ids is not None:
            model.external_ids = dict(external_ids)

        await session.commit()
        await session.refresh(model)
        return DraftRecord.from_model(model)


async def delete_draft(draft_id: str) -> bool:
    async with AsyncSessionLocal() as session:
        query = select(DraftModel).filter(DraftModel.draft_id == draft_id)
        result = await session.execute(query)
        model = result.scalar_one_or_none()
        if not model:
            return False

        await session.delete(model)
        await session.commit()
        return True
