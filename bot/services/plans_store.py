from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import or_, select

from db.models import PlanModel
from db.session import AsyncSessionLocal


@dataclass
class PlanRecord:
    plan_id: str
    created_at: str
    raw_text: str
    entries: list[dict[str, str]]
    status: str = "draft"

    @classmethod
    def from_model(cls, model: PlanModel) -> "PlanRecord":
        entries = model.entries if isinstance(model.entries, list) else []
        return cls(
            plan_id=model.plan_id,
            created_at=model.created_at.isoformat() if isinstance(model.created_at, datetime) else str(model.created_at),
            raw_text=model.raw_text,
            entries=[dict(entry) for entry in entries if isinstance(entry, dict)],
            status=model.status or "draft",
        )


async def save_plan(raw_text: str, entries: list[dict[str, str]], *, team_id: str | None = None) -> PlanRecord:
    created_at = datetime.now(timezone.utc)
    plan_id = created_at.strftime("%Y%m%d%H%M%S")

    async with AsyncSessionLocal() as session:
        model = PlanModel(
            plan_id=plan_id,
            raw_text=raw_text.strip(),
            entries=[dict(entry) for entry in entries if isinstance(entry, dict)],
            created_at=created_at,
        )
        if team_id is not None:
            model.team_id = team_id
        session.add(model)
        await session.commit()
        await session.refresh(model)
        return PlanRecord.from_model(model)


async def list_recent_plans(limit: int = 10, *, team_id: str | None = None) -> list[PlanRecord]:
    async with AsyncSessionLocal() as session:
        query = select(PlanModel).order_by(PlanModel.created_at.desc())
        if team_id is not None:
            query = query.filter(or_(PlanModel.team_id == team_id, PlanModel.team_id.is_(None)))
        query = query.limit(limit)
        result = await session.execute(query)
        models = result.scalars().all()
        return [PlanRecord.from_model(model) for model in models]


async def get_plan(plan_id: str) -> PlanRecord | None:
    async with AsyncSessionLocal() as session:
        query = select(PlanModel).filter(PlanModel.plan_id == plan_id)
        result = await session.execute(query)
        model = result.scalar_one_or_none()
        return PlanRecord.from_model(model) if model else None


async def update_plan_status(plan_id: str, status: str) -> None:
    """Update the status field of a plan (draft / activating / active / failed)."""
    async with AsyncSessionLocal() as session:
        query = select(PlanModel).filter(PlanModel.plan_id == plan_id)
        result = await session.execute(query)
        model = result.scalar_one_or_none()
        if model:
            model.status = status
            await session.commit()
