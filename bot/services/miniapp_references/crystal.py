"""Crystal-specific cross-reference enrichment."""
from __future__ import annotations

from sqlalchemy import select

from db.models import AromaCardModel
from db.session import AsyncSessionLocal

from .common import _normalize, _public_payload


async def _enrich_crystal_cross_refs(serialized: dict[str, object]) -> dict[str, object]:
    """Compute complementary oil and symptom cross-references for a crystal card.

    Crystal cards have ``complementary_oils`` (list of RU oil names).
    This resolver maps them to slugs and enriches with related symptom data.
    """
    slug = serialized.get("slug")
    if not slug:
        return serialized

    complementary_oil_names: list[str] = list(serialized.get("complementary_oils") or [])
    complementary_oil_slugs: list[str] = []

    async with AsyncSessionLocal() as session:
        # Load all aroma cards for oil name -> slug resolution
        aroma_result = await session.execute(
            select(AromaCardModel).where(AromaCardModel.category == "aroma")
        )
        aroma_models = aroma_result.scalars().all()

        # Load symptom cards for cross-referencing
        symptom_result = await session.execute(
            select(AromaCardModel).where(AromaCardModel.category == "symptom")
        )
        symptom_models = symptom_result.scalars().all()

    # Build name -> slug lookup for aroma cards
    aroma_slug_by_name: dict[str, str] = {}
    for m in aroma_models:
        payload = _public_payload(m.payload or {})
        name_ru = str(payload.get("name_ru", "")).strip()
        name_en = str(payload.get("name_en", "")).strip()
        for key in [m.name, name_ru, name_en] + list(m.aliases or []):
            if key:
                aroma_slug_by_name[_normalize(key)] = m.slug

    # Resolve complementary oil names to slugs
    for name in complementary_oil_names:
        resolved = aroma_slug_by_name.get(_normalize(name), "")
        complementary_oil_slugs.append(resolved)

    serialized["complementary_oil_slugs"] = complementary_oil_slugs

    # Find symptoms that are treated by the complementary oils (transitive cross-ref)
    related_symptom_names: list[str] = []
    related_symptom_slugs: list[str] = []
    oil_slug_set = {s for s in complementary_oil_slugs if s}

    if oil_slug_set:
        seen_symptoms: set[str] = set()
        for sym in symptom_models:
            sym_payload = _public_payload(sym.payload or {})
            recommended_oil_slugs = sym_payload.get("recommended_oil_slugs") or []
            if isinstance(recommended_oil_slugs, list):
                if oil_slug_set & set(recommended_oil_slugs):
                    if sym.slug not in seen_symptoms:
                        seen_symptoms.add(sym.slug)
                        related_symptom_names.append(sym.name)
                        related_symptom_slugs.append(sym.slug)

    serialized["related_symptom_names"] = related_symptom_names
    serialized["related_symptom_slugs"] = related_symptom_slugs

    return serialized
