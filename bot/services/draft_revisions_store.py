from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, func

from db.session import AsyncSessionLocal
from db.models import DraftRevisionModel

logger = logging.getLogger(__name__)


class DraftRevision:
    def __init__(
        self,
        id: int,
        draft_id: str,
        rev_num: int,
        payload: dict[str, Any],
        author: str,
        note: str,
        created_at: str,
        author_telegram_id: int | None = None,
    ):
        self.id = id
        self.draft_id = draft_id
        self.rev_num = rev_num
        self.payload = payload
        self.author = author
        self.note = note
        self.created_at = created_at
        self.author_telegram_id = author_telegram_id

    @classmethod
    def from_model(cls, model: DraftRevisionModel) -> DraftRevision:
        return cls(
            id=model.id,
            draft_id=model.draft_id,
            rev_num=model.rev_num,
            payload=model.payload,
            author=model.author,
            note=model.note,
            created_at=(
                model.created_at.isoformat()
                if isinstance(model.created_at, datetime)
                else str(model.created_at)
            ),
            author_telegram_id=model.author_telegram_id,
        )

    def to_dict(self) -> dict[str, Any]:
        d = {
            "id": self.id,
            "draft_id": self.draft_id,
            "rev_num": self.rev_num,
            "payload": self.payload,
            "author": self.author,
            "note": self.note,
            "created_at": self.created_at,
        }
        if self.author_telegram_id is not None:
            d["author_telegram_id"] = self.author_telegram_id
        return d


async def create_revision(
    draft_id: str,
    payload: dict[str, Any],
    author: str = "user",
    note: str = "",
    author_telegram_id: int | None = None,
) -> DraftRevision:
    """Snapshot the current payload as a new revision. Rev numbers are auto-incremented."""
    async with AsyncSessionLocal() as session:
        # Get current max rev_num for this draft
        result = await session.execute(
            select(func.max(DraftRevisionModel.rev_num)).where(
                DraftRevisionModel.draft_id == draft_id
            )
        )
        max_rev = result.scalar_one_or_none() or 0

        model = DraftRevisionModel(
            draft_id=draft_id,
            rev_num=max_rev + 1,
            payload=dict(payload),
            author=author,
            note=note,
            author_telegram_id=author_telegram_id,
            created_at=datetime.now(timezone.utc),
        )
        session.add(model)
        await session.commit()
        await session.refresh(model)
        return DraftRevision.from_model(model)


async def list_revisions(draft_id: str) -> list[DraftRevision]:
    """Return all revisions for a draft, ordered by rev_num ascending."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(DraftRevisionModel)
            .where(DraftRevisionModel.draft_id == draft_id)
            .order_by(DraftRevisionModel.rev_num.asc())
        )
        models = result.scalars().all()
        return [DraftRevision.from_model(m) for m in models]


async def get_revision(draft_id: str, rev_num: int) -> DraftRevision | None:
    """Get a specific revision by draft_id + rev_num."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(DraftRevisionModel).where(
                DraftRevisionModel.draft_id == draft_id,
                DraftRevisionModel.rev_num == rev_num,
            )
        )
        model = result.scalar_one_or_none()
        return DraftRevision.from_model(model) if model else None
