"""CRUD for the blends table."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from db.session import AsyncSessionLocal
from db.models import BlendModel

logger = logging.getLogger(__name__)


@dataclass
class BlendRecord:
    slug: str
    name: str
    goal: str = ""
    ingredients: list[dict[str, Any]] = field(default_factory=list)
    indications: str = ""
    contraindications: str = ""
    compatibility_notes: str = ""
    source_pdf: str = ""

    @classmethod
    def from_model(cls, m: BlendModel) -> BlendRecord:
        return cls(
            slug=m.slug,
            name=m.name,
            goal=m.goal,
            ingredients=m.ingredients or [],
            indications=m.indications,
            contraindications=m.contraindications,
            compatibility_notes=m.compatibility_notes,
            source_pdf=m.source_pdf,
        )


async def get_blend(slug: str) -> BlendRecord | None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(BlendModel).filter(BlendModel.slug == slug)
        )
        m = result.scalar_one_or_none()
        return BlendRecord.from_model(m) if m else None


async def list_blends(
    goal: str | None = None, limit: int = 50
) -> list[BlendRecord]:
    async with AsyncSessionLocal() as session:
        query = select(BlendModel).order_by(BlendModel.name).limit(limit)
        if goal:
            query = query.filter(BlendModel.goal.ilike(f"%{goal}%"))
        result = await session.execute(query)
        return [BlendRecord.from_model(m) for m in result.scalars().all()]


async def search_by_ingredient(oil_slug: str) -> list[BlendRecord]:
    """Find blends containing a specific oil (JSON array search)."""
    all_blends = await list_blends(limit=500)
    return [
        b for b in all_blends
        if any(
            ing.get("oil_slug") == oil_slug
            for ing in b.ingredients
        )
    ]


async def upsert_blend(
    slug: str,
    name: str,
    goal: str = "",
    ingredients: list[dict[str, Any]] | None = None,
    indications: str = "",
    contraindications: str = "",
    compatibility_notes: str = "",
    source_pdf: str = "",
) -> BlendRecord:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(BlendModel).filter(BlendModel.slug == slug)
        )
        m = result.scalar_one_or_none()
        if m is None:
            m = BlendModel(slug=slug, name=name)
            session.add(m)
        m.name = name
        m.goal = goal
        m.ingredients = ingredients or []
        m.indications = indications
        m.contraindications = contraindications
        m.compatibility_notes = compatibility_notes
        m.source_pdf = source_pdf
        m.updated_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(m)
        return BlendRecord.from_model(m)
