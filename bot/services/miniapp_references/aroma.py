"""Aroma-specific cross-reference enrichment."""
from __future__ import annotations

from sqlalchemy import select

from db.models import AromaCardModel
from db.session import AsyncSessionLocal

from .common import _extract_ru_name, _normalize, _public_payload


async def _enrich_aroma_cross_refs(serialized: dict[str, object]) -> dict[str, object]:
    """Compute blends_containing_* and complementary_oil_* cross-references for an aroma card."""
    slug = serialized.get("slug")
    if not slug:
        return serialized
    blends_containing_names: list[str] = []
    blends_containing_slugs: list[str] = []
    blends_containing_categories: list[str] = []
    complementary_oil_names: list[str] = list(serialized.get("complementary_oil_names") or [])
    complementary_oil_slugs_from_payload: list[str] = list(serialized.get("complementary_oil_slugs") or [])
    complementary_oil_slugs: list[str] = []

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(AromaCardModel).where(AromaCardModel.category == "aroma"))
        aroma_models = result.scalars().all()
        # Build lookup: normalised name/alias -> slug
        aroma_slug_by_name: dict[str, str] = {}
        aroma_slug_to_source_type: dict[str, str] = {}
        for m in aroma_models:
            aroma_slug_by_name[_normalize(m.name)] = m.slug
            aroma_slug_to_source_type[m.slug] = m.source_type or ""
            for alias in (m.aliases or []):
                aroma_slug_by_name[_normalize(alias)] = m.slug

        result2 = await session.execute(select(AromaCardModel).where(AromaCardModel.category == "blend"))
        blend_models = result2.scalars().all()
        for blend in blend_models:
            payload = _public_payload(blend.payload or {})
            ingredient_slugs = payload.get("ingredient_slugs") or []
            if isinstance(ingredient_slugs, list) and slug in ingredient_slugs:
                name_ru = str(payload.get("name_ru", "")).strip()
                blends_containing_names.append(name_ru or blend.name)
                blends_containing_slugs.append(blend.slug)
                blends_containing_categories.append(str(payload.get("blend_category", "") or ""))

    # Resolve complementary oil slugs from stored names
    for name in complementary_oil_names:
        resolved = aroma_slug_by_name.get(_normalize(name))
        complementary_oil_slugs.append(resolved or "")

    # If names list is empty but slugs are stored in payload, resolve names from slugs
    if not complementary_oil_names and complementary_oil_slugs_from_payload:
        slug_to_name = {m.slug: m.name for m in aroma_models}
        for s in complementary_oil_slugs_from_payload:
            if s and s in slug_to_name:
                complementary_oil_names.append(slug_to_name[s])
                complementary_oil_slugs.append(s)

    complementary_oil_source_types = [aroma_slug_to_source_type.get(s, "") for s in complementary_oil_slugs]

    serialized["blends_containing_names"] = blends_containing_names
    serialized["blends_containing_slugs"] = blends_containing_slugs
    serialized["blends_containing_categories"] = blends_containing_categories
    serialized["complementary_oil_names"] = complementary_oil_names
    serialized["complementary_oil_slugs"] = complementary_oil_slugs
    serialized["complementary_oil_source_types"] = complementary_oil_source_types

    # Find symptoms where this oil is recommended (cross-ref back)
    related_symptom_names: list[str] = []
    related_symptom_slugs: list[str] = []
    related_symptom_parent_groups: list[str] = []
    async with AsyncSessionLocal() as session:
        sym_result = await session.execute(select(AromaCardModel).where(AromaCardModel.category == "symptom"))
        symptom_models = sym_result.scalars().all()
    for sym in symptom_models:
        sym_payload = _public_payload(sym.payload or {})
        oil_slugs_in_sym = sym_payload.get("recommended_oil_slugs") or []
        if isinstance(oil_slugs_in_sym, list) and slug in oil_slugs_in_sym:
            related_symptom_names.append(sym.name)
            related_symptom_slugs.append(sym.slug)
            related_symptom_parent_groups.append(str(sym_payload.get("parent_group", "") or ""))
    serialized["related_symptom_names"] = related_symptom_names
    serialized["related_symptom_slugs"] = related_symptom_slugs
    serialized["related_symptom_parent_groups"] = related_symptom_parent_groups
    return serialized
