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
        seq_id: int = 0,
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

    @classmethod
    def from_model(cls, model: DraftModel) -> DraftRecord:
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


async def list_recent_drafts(limit: int = 10, kind: str | None = None) -> list[DraftRecord]:
    async with AsyncSessionLocal() as session:
        query = select(DraftModel).order_by(DraftModel.id.asc()).limit(limit)
        if kind:
            query = query.filter(DraftModel.kind == kind)
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


async def update_draft(
    draft_id: str,
    *,
    topic: str | None = None,
    status: str | None = None,
    feedback: str | None = None,
    payload: dict[str, Any] | None = None,
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
            # SQLAlchemy JSON columns sometimes need explicit flagging to track mutations
            # Reassigning a new dict usually works best
            model.payload = dict(payload)
            
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
