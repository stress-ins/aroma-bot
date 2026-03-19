"""Blend-specific cross-reference enrichment."""
from __future__ import annotations

from sqlalchemy import select

from db.models import AromaCardModel
from db.session import AsyncSessionLocal

from .common import _public_payload


async def _enrich_blend_cross_refs(serialized: dict[str, object]) -> dict[str, object]:
    """Find symptoms where this blend is recommended (cross-ref back)."""
    slug = serialized.get("slug")
    if not slug:
        return serialized
    related_symptom_names: list[str] = []
    related_symptom_slugs: list[str] = []
    async with AsyncSessionLocal() as session:
        sym_result = await session.execute(select(AromaCardModel).where(AromaCardModel.category == "symptom"))
        symptom_models = sym_result.scalars().all()
    for sym in symptom_models:
        sym_payload = _public_payload(sym.payload or {})
        blend_slugs_in_sym = sym_payload.get("recommended_blend_slugs") or []
        if isinstance(blend_slugs_in_sym, list) and slug in blend_slugs_in_sym:
            related_symptom_names.append(sym.name)
            related_symptom_slugs.append(sym.slug)
    serialized["related_symptom_names"] = related_symptom_names
    serialized["related_symptom_slugs"] = related_symptom_slugs
    return serialized
