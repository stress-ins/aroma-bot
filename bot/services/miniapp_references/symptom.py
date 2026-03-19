"""Symptom-specific cross-reference enrichment."""
from __future__ import annotations

from sqlalchemy import select

from db.models import AromaCardModel
from db.session import AsyncSessionLocal

from .common import _extract_ru_name, _normalize, _public_payload, _SYMPTOM_STOP_WORDS


async def _enrich_symptom_cross_refs(serialized: dict[str, object]) -> dict[str, object]:
    """Resolve recommended oil/blend names to Russian + slugs for a symptom card.

    Uses stored recommended_oil_slugs as primary source (already resolved during import).
    Filters stop-words/artifacts from the names list.
    """
    raw_oil_names: list[str] = list(serialized.get("recommended_oil_names") or [])
    stored_oil_slugs: list[str] = list(serialized.get("recommended_oil_slugs") or [])
    raw_blend_names: list[str] = list(serialized.get("recommended_blend_names") or [])
    stored_blend_slugs: list[str] = list(serialized.get("recommended_blend_slugs") or [])

    async with AsyncSessionLocal() as session:
        aroma_result = await session.execute(select(AromaCardModel).where(AromaCardModel.category == "aroma"))
        aroma_models = aroma_result.scalars().all()
        blend_result = await session.execute(select(AromaCardModel).where(AromaCardModel.category == "blend"))
        blend_models = blend_result.scalars().all()

    aroma_slug_to_name: dict[str, str] = {}
    aroma_name_to_slug: dict[str, str] = {}
    for m in aroma_models:
        payload = _public_payload(m.payload or {})
        name_ru = str(payload.get("name_ru", "")).strip()
        display_name = name_ru or m.name
        aroma_slug_to_name[m.slug] = display_name
        # Build reverse lookup: normalized English + Russian + aliases -> slug
        for alias in [m.name, name_ru] + list(m.aliases or []):
            if alias:
                aroma_name_to_slug[_normalize(alias)] = m.slug
    blend_slug_to_name: dict[str, str] = {}
    for m in blend_models:
        payload = _public_payload(m.payload or {})
        name_ru = str(payload.get("name_ru", "")).strip()
        blend_slug_to_name[m.slug] = name_ru or m.name

    # Strategy: zip stored names + slugs, filter stop-words/artifacts, resolve RU names via slug
    oil_names: list[str] = []
    oil_slugs: list[str] = []
    seen: set[str] = set()
    for i, raw_name in enumerate(raw_oil_names):
        name = str(raw_name).strip()
        if not name or name.lower() in _SYMPTOM_STOP_WORDS or len(name) > 60:
            continue
        # Skip items that start with bullet/dot (application instructions)
        if name.startswith(("\u2022", ".", "-", "\u00b7")):
            continue
        slug = stored_oil_slugs[i] if i < len(stored_oil_slugs) else ""
        # If no slug stored, resolve via name lookup (handles English-named imports)
        if not slug:
            slug = aroma_name_to_slug.get(_normalize(name), "")
        if slug and slug in seen:
            continue
        if slug:
            seen.add(slug)
        # Prefer Russian name from aroma DB; fall back to extracted/raw name
        db_display = aroma_slug_to_name.get(slug, "") if slug else ""
        # Validate DB name is not a garbage artifact (starts with bullet/dot/etc.)
        if db_display and not db_display.startswith(("\u2022", ".", "-", "\u00b7")):
            display = db_display
        else:
            display = _extract_ru_name(name) if "(" in name else name
        oil_names.append(display)
        oil_slugs.append(slug)

    # Do the same for blend recommendations
    blend_names: list[str] = []
    blend_slugs: list[str] = []
    seen_blends: set[str] = set()
    for i, raw_name in enumerate(raw_blend_names):
        name = str(raw_name).strip()
        if not name or name.lower() in _SYMPTOM_STOP_WORDS or len(name) > 60:
            continue
        if name.startswith(("\u2022", ".", "-", "\u00b7")):
            continue
        slug = stored_blend_slugs[i] if i < len(stored_blend_slugs) else ""
        if slug and slug in seen_blends:
            continue
        if slug:
            seen_blends.add(slug)
        display = blend_slug_to_name.get(slug, "") if slug else ""
        if not display:
            display = _extract_ru_name(name) if "(" in name else name
        blend_names.append(display)
        blend_slugs.append(slug)

    serialized["recommended_oil_names"] = oil_names
    serialized["recommended_oil_slugs"] = oil_slugs
    serialized["recommended_blend_names"] = blend_names
    serialized["recommended_blend_slugs"] = blend_slugs
    return serialized
