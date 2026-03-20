"""Symptom-specific cross-reference enrichment."""
from __future__ import annotations

import re

from sqlalchemy import select

from db.models import AromaCardModel
from db.session import AsyncSessionLocal

from .common import _extract_ru_name, _normalize, _public_payload, _SYMPTOM_STOP_WORDS

# Alias map: variant product names → canonical slug in DB
_OIL_NAME_ALIASES: dict[str, str] = {
    "sacred frankincense": "sacred-frankincense",
    "frereana frankincense": "frankincense",
    "eucalyptus blue": "eucaliptus-blue",
    "eucalyptus radiata": "ravintsara",
    "balsam fir idaho": "balsam-fir",
    "idaho balsam fir": "balsam-fir",
    "idaho blue spruce": "blue-spruce",
    "northern lights black spruce": "black-spruce",
    "cinnamon bark": "cinnamon",
    "tea tree melaleuca alternifolia": "tea-tree",
    "amazonian ylang ylang": "ylang-ylang",
    "plectranthus oregano": "oregano",
    # Simple English names → slug (cards exist in DB)
    "basil": "basil",
    "bay laurel": "bay-laurel",
    "laurus nobilis": "bay-laurel",
    "carrot seed": "carrot-seed",
    "cypress": "cypress",
    "dill": "dill",
    "fennel": "fennel",
    "ginger": "ginger",
    "juniper": "juniper",
    "myrrh": "myrrh",
    "мирра": "myrrh",
    "neroli": "neroli",
    "rosemary": "rosemary",
    "sandalwood": "sandalwood",
    "clary sage": "clary-sage",
    "elemi": "elemi",
}

# Regex for garbage entries from PDF parser
_GARBAGE_RE = re.compile(
    r"^[(*•^_]"             # starts with (, *, •, ^, _
    r"|РЕКОМЕНДАЦИИ"         # section header leaked into names
    r"|  "                   # double space — glued tokens
    r"|\)$"                  # trailing paren without opening (e.g. "Иланг-иланг)")
)

# OCR prefix pattern: 1-3 lowercase letters (or punctuation) + space + uppercase start
# e.g. "wk Copaiba", "чк Clove", "^k Fennel", "k Cistus", "w- Lemon", "i Rosemary"
_OCR_PREFIX_RE = re.compile(
    r"^[a-zа-яё~\-'^]{1,3}\s+[A-ZА-ЯЁ]"
)


def _is_garbage_name(name: str) -> bool:
    """Return True if ``name`` looks like a PDF-parser artifact, not a real oil/blend name."""
    if len(name) < 3:
        return True
    if _GARBAGE_RE.search(name):
        return True
    # OCR column-bleed prefixes: "wk Copaiba", "чк Clove", etc.
    if _OCR_PREFIX_RE.match(name):
        return True
    # Russian sentences / book instructions: long strings starting with lowercase
    if len(name) > 30 and name[0].islower():
        return True
    return False


async def _enrich_symptom_cross_refs(serialized: dict[str, object]) -> dict[str, object]:
    """Resolve recommended oil/blend names to Russian + slugs for a symptom card.

    Uses stored recommended_oil_slugs as primary source (already resolved during import).
    Filters stop-words/artifacts from the names list.
    Drops entries that cannot be resolved to a valid slug.
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
        name_en = str(payload.get("name_en", "")).strip()
        display_name = name_ru or m.name
        aroma_slug_to_name[m.slug] = display_name
        # Build reverse lookup: normalized English + Russian + name_en + aliases -> slug
        for alias in [m.name, name_ru, name_en] + list(m.aliases or []):
            if alias:
                aroma_name_to_slug[_normalize(alias)] = m.slug

    blend_slug_to_name: dict[str, str] = {}
    blend_name_to_slug: dict[str, str] = {}
    for m in blend_models:
        payload = _public_payload(m.payload or {})
        name_ru = str(payload.get("name_ru", "")).strip()
        name_en = str(payload.get("name_en", "")).strip()
        blend_slug_to_name[m.slug] = name_ru or m.name
        for alias in [m.name, name_ru, name_en] + list(m.aliases or []):
            if alias:
                blend_name_to_slug[_normalize(alias)] = m.slug

    # Strategy: zip stored names + slugs, filter garbage/stop-words, resolve RU names via slug
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
        # Skip garbage entries from PDF parser
        if _is_garbage_name(name):
            continue
        slug = stored_oil_slugs[i] if i < len(stored_oil_slugs) else ""
        # If no slug stored, resolve via name lookup (handles English-named imports)
        if not slug:
            norm = _normalize(name)
            slug = aroma_name_to_slug.get(norm, "")
            # Try alias map for variant product names
            if not slug:
                alias_slug = _OIL_NAME_ALIASES.get(norm)
                if alias_slug:
                    slug = alias_slug
            # Check if this is actually a blend (e.g. Valor, PanAway)
            if not slug:
                blend_slug = blend_name_to_slug.get(norm, "")
                if blend_slug:
                    # Move to blend list instead
                    if blend_slug not in seen:
                        seen.add(blend_slug)
                        blend_display = blend_slug_to_name.get(blend_slug, name)
                        raw_blend_names.append(blend_display)
                        stored_blend_slugs.append(blend_slug)
                    continue
        # Drop entries that could not be resolved to a valid slug
        if not slug:
            continue
        if slug in seen:
            continue
        seen.add(slug)
        # Prefer Russian name from aroma DB; fall back to extracted/raw name
        db_display = aroma_slug_to_name.get(slug, "")
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
        if _is_garbage_name(name):
            continue
        slug = stored_blend_slugs[i] if i < len(stored_blend_slugs) else ""
        if not slug:
            slug = blend_name_to_slug.get(_normalize(name), "")
        if not slug:
            continue
        if slug in seen_blends:
            continue
        seen_blends.add(slug)
        display = blend_slug_to_name.get(slug, "")
        if not display:
            display = _extract_ru_name(name) if "(" in name else name
        blend_names.append(display)
        blend_slugs.append(slug)

    serialized["recommended_oil_names"] = oil_names
    serialized["recommended_oil_slugs"] = oil_slugs
    serialized["recommended_blend_names"] = blend_names
    serialized["recommended_blend_slugs"] = blend_slugs
    return serialized
