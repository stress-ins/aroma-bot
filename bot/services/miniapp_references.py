from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from sqlalchemy import select

from bot.agents.reference_experts import enrich_reference_card_sync
from db.models import AromaCardModel
from db.session import AsyncSessionLocal


BASE_DIR = Path(__file__).resolve().parents[2]
SEED_FILE = BASE_DIR / "data" / "reference_cards_seed.json"
EXTRA_SEED_FILE = BASE_DIR / "data" / "reference_cards_extra.json"
REFERENCE_CATEGORIES = {"aroma", "practice", "sound", "concept", "blend", "symptom"}
REFERENCE_IMAGES_DIR = BASE_DIR / "assets" / "reference_images"
INTERNAL_SEED_KEY = "__seed_payload"
INTERNAL_OVERRIDES_KEY = "__manual_overrides"
REFERENCE_CONTEXT_TITLES = {
    "aroma": "Ароматы",
    "concept": "Теория",
    "practice": "Практики",
    "sound": "Звуки",
}
EDITABLE_FIELDS = (
    "description",
    "description_short",
    "questions",
    "nps_effect",
    "therapeutic_properties",
    "psychological_properties",
    "history",
    "volatility",
    "botanical_family",
    "origin_countries",
    "extraction_method",
    "key",
    "applications",
)
RESOURCE_FIELDS = ("plus", "minus")
SHARED_IMAGE_OVERRIDES = {
    ("practice", "breath"): "nature.jpg",
    ("practice", "meditation"): "nature.jpg",
    ("practice", "body"): "nature.jpg",
    ("concept", "method"): "nature.jpg",
    ("concept", "chakra"): "nature.jpg",
    ("sound", "instrument"): "instrument.jpg",
    ("sound", "sound"): "sound.jpg",
    ("sound", "voice"): "voice.jpg",
}
SLUG_SHARED_OVERRIDES = {
    ("sound", "nature-sounds"): "nature.jpg",
    ("sound", "silence-practice"): "nature.jpg",
}


def _normalize(value: str) -> str:
    return " ".join(value.lower().replace("ё", "е").replace('"', "").split())


def _image_label(category: str) -> str:
    return {
        "aroma": "источник сырья",
        "practice": "образ практики",
        "concept": "теоретическая карточка",
        "sound": "источник звука",
    }.get(category, "справочник")


def _source_illustration_key(source_type: str, title: str) -> str:
    normalized = _normalize(title)
    if any(token in normalized for token in ("апельсин", "orange", "мандарин", "mandarin", "лимон", "lemon", "лайм", "lime", "грейпфрут", "grapefruit", "бергамот", "bergamot")):
        return "citrus-slice"
    if any(token in normalized for token in ("лаванда", "lavender")):
        return "lavender-sprig"
    if any(token in normalized for token in ("мята", "peppermint", "базилик", "basil", "лемонграсс", "fennel")):
        return "leafy-herb"
    if any(token in normalized for token in ("эвкалипт", "eucalyptus", "кедр", "cedar", "кипарис", "cypress", "пихта", "fir", "ель", "spruce", "можжевельник", "juniper")):
        return "branch"
    if any(token in normalized for token in ("роза", "rose", "жасмин", "jasmine", "нероли", "neroli", "ромашка", "chamomile", "иланг", "ylang", "герань", "geranium")):
        return "flower"
    if any(token in normalized for token in ("ладан", "frankincense", "копаиба", "copaiba", "сандал", "sandal", "пачули", "patchouli")):
        return "resin-drop"
    if any(token in normalized for token in ("корица", "cinnamon", "гвоздика", "clove", "имбирь", "ginger", "перец", "cassia", "oregano", "тимьян", "thyme")):
        return "spice"

    fallback = {
        "citrus": "citrus-slice",
        "flower": "flower",
        "tree": "branch",
        "resin": "resin-drop",
        "spice": "spice",
        "herb": "leafy-herb",
        "grass": "leafy-herb",
        "breath": "breath-wave",
        "meditation": "meditation-stone",
        "body": "body-line",
        "method": "breath-wave",
        "chakra": "meditation-stone",
        "system": "sound-wave",
        "founder": "voice-wave",
        "energy": "body-line",
        "sound": "sound-wave",
        "instrument": "sound-bowl",
        "voice": "voice-wave",
    }
    return fallback.get(source_type, "leafy-herb")


def _source_motif_svg(source_type: str, title: str) -> str:
    motif = _source_illustration_key(source_type, title)
    if motif == "citrus-slice":
        return """
      <circle cx='498' cy='242' r='92' fill='#f39b2f' />
      <circle cx='498' cy='242' r='76' fill='#ffd67f' />
      <circle cx='498' cy='242' r='18' fill='#fff6df' />
      <path d='M498 166v152M422 242h152M444 188l108 108M552 188l-108 108' stroke='#fff6df' stroke-width='10' stroke-linecap='round' />
      <ellipse cx='420' cy='132' rx='34' ry='16' fill='#6f9f55' transform='rotate(-18 420 132)' />
        """.strip()
    if motif == "lavender-sprig":
        return """
      <path d='M468 322c22-54 44-118 48-164' stroke='#638356' stroke-width='10' stroke-linecap='round' />
      <path d='M508 182c-22-18-18-44 6-54 18 16 18 41-6 54Z' fill='#8f78c7' />
      <path d='M490 208c-22-18-18-44 6-54 18 16 18 41-6 54Z' fill='#8066bc' />
      <path d='M520 214c-22-18-18-44 6-54 18 16 18 41-6 54Z' fill='#9a85d2' />
      <path d='M484 242c-22-18-18-44 6-54 18 16 18 41-6 54Z' fill='#8f78c7' />
      <path d='M514 248c-22-18-18-44 6-54 18 16 18 41-6 54Z' fill='#8066bc' />
      <path d='M478 276c-22-18-18-44 6-54 18 16 18 41-6 54Z' fill='#9a85d2' />
        """.strip()
    if motif == "leafy-herb":
        return """
      <path d='M486 324c-8-64 6-130 32-184' stroke='#5d8c63' stroke-width='10' stroke-linecap='round' />
      <ellipse cx='460' cy='252' rx='40' ry='18' fill='#7eaf7d' transform='rotate(-34 460 252)' />
      <ellipse cx='526' cy='220' rx='42' ry='18' fill='#88bb86' transform='rotate(28 526 220)' />
      <ellipse cx='452' cy='188' rx='38' ry='16' fill='#6c9d6c' transform='rotate(-48 452 188)' />
      <ellipse cx='534' cy='164' rx='38' ry='16' fill='#79aa79' transform='rotate(24 534 164)' />
        """.strip()
    if motif == "branch":
        return """
      <path d='M454 320c20-76 36-126 70-184' stroke='#6e8f55' stroke-width='12' stroke-linecap='round' />
      <path d='M484 258c-18-12-38-14-60-6 12-24 30-34 54-30' fill='#88aa67' />
      <path d='M520 230c-12-18-28-30-50-36 24-6 44 0 60 18' fill='#7d9c5f' />
      <path d='M500 184c-12-18-28-30-50-36 24-6 44 0 60 18' fill='#95b474' />
        """.strip()
    if motif == "flower":
        return """
      <circle cx='498' cy='236' r='20' fill='#f2c86a' />
      <ellipse cx='498' cy='180' rx='28' ry='42' fill='#d78aa7' />
      <ellipse cx='550' cy='236' rx='42' ry='28' fill='#e5a0ba' />
      <ellipse cx='498' cy='292' rx='28' ry='42' fill='#cf7f9e' />
      <ellipse cx='446' cy='236' rx='42' ry='28' fill='#e9afc5' />
      <path d='M498 320c0-34-2-58 8-88' stroke='#6d9558' stroke-width='10' stroke-linecap='round' />
        """.strip()
    if motif == "resin-drop":
        return """
      <path d='M500 140c36 50 64 86 64 132 0 42-28 76-64 76s-64-34-64-76c0-46 28-82 64-132Z' fill='#c98a55' />
      <path d='M500 176c24 34 40 58 40 92 0 22-16 42-40 42' fill='none' stroke='#efc59a' stroke-width='10' stroke-linecap='round' />
        """.strip()
    if motif == "spice":
        return """
      <rect x='428' y='214' width='132' height='22' rx='11' fill='#b86f40' transform='rotate(-12 494 225)' />
      <rect x='438' y='252' width='126' height='22' rx='11' fill='#c67f4f' transform='rotate(10 501 263)' />
      <circle cx='548' cy='178' r='16' fill='#8b4e2e' />
      <circle cx='520' cy='162' r='12' fill='#9b5b39' />
        """.strip()
    if motif == "sound-wave":
        return """
      <path d='M430 262c24-28 40-42 68-56 34-18 64-22 122-18' stroke='#6479c0' stroke-width='12' stroke-linecap='round' fill='none' />
      <path d='M446 298c28-22 56-34 88-38 26-4 52-2 86 8' stroke='#8ea0dd' stroke-width='10' stroke-linecap='round' fill='none' />
        """.strip()
    if motif == "sound-bowl":
        return """
      <path d='M424 262c18 44 56 70 104 70s86-26 104-70H424Z' fill='#a67d58' />
      <rect x='486' y='332' width='24' height='34' rx='10' fill='#8a6748' />
      <rect x='454' y='364' width='88' height='16' rx='8' fill='#7a5b42' />
        """.strip()
    if motif == "voice-wave":
        return """
      <circle cx='454' cy='244' r='28' fill='#b874aa' />
      <path d='M500 244c18-28 34-40 62-46 18-4 36-2 56 8' stroke='#b874aa' stroke-width='10' stroke-linecap='round' fill='none' />
      <path d='M506 276c22-10 44-14 66-10 16 2 30 8 44 18' stroke='#d199c7' stroke-width='8' stroke-linecap='round' fill='none' />
        """.strip()
    if motif == "breath-wave":
        return """
      <path d='M414 252c44-28 76-42 114-42 42 0 82 14 132 44' stroke='#6ea7d0' stroke-width='12' stroke-linecap='round' fill='none' />
      <path d='M432 294c34 12 62 18 92 18 44 0 82-12 128-38' stroke='#9ec9e5' stroke-width='10' stroke-linecap='round' fill='none' />
        """.strip()
    if motif == "meditation-stone":
        return """
      <ellipse cx='492' cy='316' rx='104' ry='26' fill='#dcccb8' />
      <ellipse cx='494' cy='278' rx='74' ry='22' fill='#b9a48a' />
      <ellipse cx='500' cy='238' rx='46' ry='18' fill='#8f7d69' />
        """.strip()
    if motif == "body-line":
        return """
      <path d='M498 164c20 0 34 16 34 36 0 18-12 32-28 36l8 92c2 18-12 34-30 34-18 0-32-16-30-34l8-92c-16-4-28-18-28-36 0-20 14-36 34-36Z' fill='#d7a0a0' />
        """.strip()
    return ""


def _source_image(source_type: str, title: str, category: str) -> str:
    palette = {
        "citrus": ("#f6a623", "#ffe3a1", "цитрус"),
        "flower": ("#d36a8b", "#f6d5de", "цветок"),
        "tree": ("#5e7d3a", "#d7e5b8", "дерево"),
        "resin": ("#8a5a3c", "#e4c9b0", "смола"),
        "spice": ("#b56134", "#f0cfb8", "специя"),
        "herb": ("#5d8c63", "#d7edd9", "трава"),
        "grass": ("#4f8b57", "#d4ecd7", "трава"),
        "breath": ("#4d8cbf", "#d7e8f7", "дыхание"),
        "meditation": ("#7a64b1", "#e2daf7", "медитация"),
        "body": ("#b35f5f", "#f4d9d9", "тело"),
        "method": ("#6a8f7a", "#deefe6", "метод"),
        "chakra": ("#8a63c2", "#e7def8", "чакра"),
        "system": ("#5878b8", "#dde7fb", "система"),
        "founder": ("#a86e57", "#f0dfd5", "автор"),
        "energy": ("#d08a4f", "#f8e4cf", "энергия"),
        "sound": ("#5468b8", "#dbe1fb", "звук"),
        "instrument": ("#8b6e4a", "#eadcc9", "инструмент"),
        "voice": ("#ad5f9e", "#f0d7eb", "голос"),
        "blend": ("#b45c3d", "#f2e2d8", "смесь"),
        "symptom": ("#7a4f8a", "#e9ddf5", "симптом"),
    }
    primary, secondary, label = palette.get(source_type, palette["herb"])
    card_label = _image_label(category)
    motif = _source_motif_svg(source_type, title)
    # Only show "source of oil" hint for aroma cards; other categories get category label instead
    if category == "aroma":
        category_hint = f"<text x='54' y='262' font-size='18' font-family='Arial' fill='#8a7565'>Что является источником этого масла</text>"
    else:
        category_hint = ""
    svg = f"""
    <svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 640 420'>
      <defs>
        <linearGradient id='g' x1='0' x2='1' y1='0' y2='1'>
          <stop offset='0%' stop-color='{secondary}' />
          <stop offset='100%' stop-color='#fffaf4' />
        </linearGradient>
      </defs>
      <rect width='640' height='420' rx='32' fill='url(#g)' />
      <circle cx='510' cy='86' r='54' fill='{primary}' fill-opacity='0.16' />
      <circle cx='118' cy='330' r='80' fill='{primary}' fill-opacity='0.11' />
      <rect x='54' y='58' width='220' height='34' rx='17' fill='{primary}' fill-opacity='0.18' />
      <text x='74' y='81' font-size='18' font-family='Arial' fill='{primary}'>{label}</text>
      <text x='54' y='176' font-size='42' font-family='Arial' font-weight='700' fill='#2d241e'>{title}</text>
      <text x='54' y='224' font-size='22' font-family='Arial' fill='#6a5a4a'>{card_label}</text>
      {category_hint}
      {motif}
    </svg>
    """.strip()
    return f"data:image/svg+xml;charset=UTF-8,{quote(svg)}"


def _payload_image_url(payload: dict[str, object]) -> str | None:
    """Return payload image_url if it points to an existing file on disk."""
    stored = str(payload.get("image_url", "") or "").strip()
    if not stored or stored.startswith("data:"):
        return None
    # Resolve /reference-images/... to assets/reference_images/...
    if stored.startswith("/reference-images/"):
        rel = stored[len("/reference-images/"):]
        candidate = REFERENCE_IMAGES_DIR / rel
        if candidate.exists():
            return stored
    return None


def _serialize_model(model: AromaCardModel) -> dict[str, object]:
    payload = _public_payload(model.payload or {})
    payload.setdefault("resource_values", {"plus": "", "minus": ""})
    payload["slug"] = model.slug
    # For blend cards: use Russian name as primary, keep English as name_en
    if model.category == "blend":
        name_ru = str(payload.get("name_ru", "")).strip()
        payload["name"] = name_ru or model.name
        payload["name_en"] = model.name if name_ru else ""
    else:
        payload["name"] = model.name
    payload["category"] = model.category
    payload["aliases"] = list(model.aliases or [])
    payload["source_type"] = model.source_type
    # For blend cards: extract Russian ingredient names from "English (Russian)" patterns
    if model.category == "blend":
        raw_ingredient_names = list(payload.get("ingredient_names") or [])
        ingredient_names_ru = []
        for n in raw_ingredient_names:
            s = str(n).strip()
            if not s or len(s) > 60:
                continue
            if re.search(r"\.\s+[A-ZА-Я]", s):
                continue
            # Only keep items that look like oil names (have parentheses or are short single-word names)
            if "(" in s and ")" in s:
                ingredient_names_ru.append(_extract_ru_name(s))
        payload["ingredient_names_ru"] = ingredient_names_ru
    payload["image_url"] = (
        _payload_image_url(payload)
        or _local_reference_image_url(model.category, model.slug)
        or _shared_reference_image_url(model.category, model.slug, model.source_type)
        or _source_image(model.source_type, str(payload.get("name") or model.name), model.category)
    )
    payload["image_alt"] = f"{model.name}: {_image_label(model.category)}"
    return payload


def _public_payload(payload: dict[str, object]) -> dict[str, object]:
    public = dict(payload or {})
    public.pop(INTERNAL_SEED_KEY, None)
    public.pop(INTERNAL_OVERRIDES_KEY, None)
    return public


def _compact_reference_detail(payload: dict[str, object], *, max_chars: int = 140) -> str:
    for field in (
        "psychological_properties",
        "therapeutic_properties",
        "description",
        "course_notes",
        "history",
    ):
        value = str(payload.get(field, "") or "").strip()
        if value:
            return value[:max_chars]
    return ""


def _seeded_payload(seed_payload: dict[str, object], overrides: set[str] | None = None) -> dict[str, object]:
    payload = dict(seed_payload)
    payload[INTERNAL_SEED_KEY] = dict(seed_payload)
    payload[INTERNAL_OVERRIDES_KEY] = sorted(overrides or set())
    return payload


def _merge_seed_into_existing(existing_payload: dict[str, object], seed_payload: dict[str, object]) -> dict[str, object]:
    current_public = _public_payload(existing_payload)
    overrides = set(existing_payload.get(INTERNAL_OVERRIDES_KEY, []))
    merged = dict(seed_payload)

    for field in EDITABLE_FIELDS:
        if field in overrides and field in current_public:
            merged[field] = current_public.get(field, "")

    seed_resources = dict(seed_payload.get("resource_values", {}) or {})
    current_resources = dict(current_public.get("resource_values", {}) or {})
    for field in RESOURCE_FIELDS:
        if f"resource_values.{field}" in overrides:
            seed_resources[field] = current_resources.get(field, "")
    if seed_resources:
        merged["resource_values"] = seed_resources

    return _seeded_payload(merged, overrides)


def _local_reference_image_url(category: str, slug: str) -> str | None:
    for extension in ("jpg", "jpeg", "png", "webp"):
        candidate = REFERENCE_IMAGES_DIR / f"{category}s" / f"{slug}.{extension}"
        if candidate.exists():
            return f"/reference-images/{category}s/{slug}.{extension}"
    return None


def _shared_reference_image_url(category: str, slug: str, source_type: str) -> str | None:
    shared_name = SLUG_SHARED_OVERRIDES.get((category, slug)) or SHARED_IMAGE_OVERRIDES.get((category, source_type))
    if not shared_name:
        return None
    candidate = REFERENCE_IMAGES_DIR / "shared" / shared_name
    if candidate.exists():
        return f"/reference-images/shared/{shared_name}"
    return None


def _load_seed_items() -> list[dict[str, object]]:
    # These JSON files are seed inputs for reference cards only.
    # Runtime source of truth remains the database rows in aroma_cards.
    items: list[dict[str, object]] = []
    for path in (SEED_FILE, EXTRA_SEED_FILE):
        if not path.exists():
            continue
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(loaded, list):
            items.extend(item for item in loaded if isinstance(item, dict) and item.get("slug") and item.get("name"))
    return items


async def seed_reference_cards_if_empty() -> None:
    items = _load_seed_items()
    if not items:
        return
    async with AsyncSessionLocal() as session:
        existing_rows = await session.execute(select(AromaCardModel))
        existing_models = existing_rows.scalars().all()
        existing_by_slug = {model.slug: model for model in existing_models}
        now = datetime.now(timezone.utc)
        for item in items:
            slug = str(item["slug"])
            # Prevent symptom source_type items from defaulting to "aroma" category
            default_cat = "symptom" if str(item.get("source_type", "")).lower() == "symptom" else "aroma"
            category = str(item.get("category") or default_cat)
            aliases = list(item.get("aliases", []))
            payload = dict(item)
            existing = existing_by_slug.get(slug)
            if existing:
                changed = False
                if existing.category != category:
                    existing.category = category
                    changed = True
                if existing.name != str(item["name"]):
                    existing.name = str(item["name"])
                    changed = True
                if existing.source_type != str(item.get("source_type", "herb")):
                    existing.source_type = str(item.get("source_type", "herb"))
                    changed = True
                if list(existing.aliases or []) != aliases:
                    existing.aliases = aliases
                    changed = True
                merged_payload = _merge_seed_into_existing(dict(existing.payload or {}), payload)
                if dict(existing.payload or {}) != merged_payload:
                    existing.payload = merged_payload
                    changed = True
                if changed:
                    existing.updated_at = now
                continue
            session.add(
                AromaCardModel(
                    category=category,
                    slug=slug,
                    name=str(item["name"]),
                    source_type=str(item.get("source_type", "herb")),
                    aliases=aliases,
                    payload=_seeded_payload(payload),
                    created_at=now,
                    updated_at=now,
                )
            )
        await session.commit()


_SVG_PREFIX = "data:image/svg+xml"


async def list_reference_cards_with_placeholder_images(category: str) -> list[dict[str, str]]:
    """Return cards whose resolved image_url is an SVG placeholder."""
    await seed_reference_cards_if_empty()
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(AromaCardModel).where(AromaCardModel.category == category))
        models = result.scalars().all()
    items = []
    for model in models:
        serialized = _serialize_model(model)
        image_url = str(serialized.get("image_url", "") or "")
        if not image_url or image_url.startswith(_SVG_PREFIX):
            items.append({
                "slug": model.slug,
                "name": model.name,
                "category": model.category,
                "source_type": model.source_type,
                "image_url": image_url[:80] + "…" if len(image_url) > 80 else image_url,
            })
    return sorted(items, key=lambda x: _normalize(x["name"]))


async def list_reference_cards(category: str) -> list[dict[str, str]]:
    await seed_reference_cards_if_empty()
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(AromaCardModel).where(AromaCardModel.category == category))
        models = result.scalars().all()
    models = sorted(models, key=lambda item: _normalize(item.name))
    items = []
    for model in models:
        payload = _public_payload(model.payload or {})
        name_ru = str(payload.get("name_ru", "")).strip()
        items.append({
            "slug": model.slug,
            "name": name_ru or model.name,
            "name_en": model.name if name_ru else "",
            "description": str(payload.get("description", "")),
            "category": model.category,
            "source_type": model.source_type,
            # Extra fields used by frontend search / grouping
            "conditions_for_use": str(payload.get("conditions_for_use", "")),
            "category_group": str(payload.get("category_group", "")),
            "parent_group": str(payload.get("parent_group", "")),
            "blend_category": str(payload.get("blend_category", "")),
        })
    return items


async def list_reference_cards_missing_description(category: str) -> list[dict[str, str]]:
    """Return cards where description (and description_short) are empty — for content audit."""
    await seed_reference_cards_if_empty()
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(AromaCardModel).where(AromaCardModel.category == category))
        models = result.scalars().all()
    items = []
    for model in models:
        payload = _public_payload(model.payload or {})
        description = str(payload.get("description", "") or "").strip()
        description_short = str(payload.get("description_short", "") or "").strip()
        course_notes = str(payload.get("course_notes", "") or "").strip()
        if not description and not description_short and not course_notes:
            items.append({
                "slug": model.slug,
                "name": model.name,
                "category": model.category,
                "source_type": model.source_type,
                "description": "",
            })
    return sorted(items, key=lambda x: _normalize(x["name"]))


async def build_reference_context(
    *,
    categories: tuple[str, ...] | None = None,
    max_items_per_category: int = 6,
    max_total_chars: int = 1800,
) -> str:
    await seed_reference_cards_if_empty()
    category_order = tuple(categories or REFERENCE_CONTEXT_TITLES.keys())
    allowed_categories = tuple(category for category in category_order if category in REFERENCE_CATEGORIES)
    if not allowed_categories:
        return ""

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(AromaCardModel).where(AromaCardModel.category.in_(allowed_categories)))
        models = result.scalars().all()

    grouped: dict[str, list[str]] = {category: [] for category in allowed_categories}
    for model in sorted(models, key=lambda item: (str(item.category or ""), _normalize(item.name))):
        category = str(model.category or "")
        if category not in grouped or len(grouped[category]) >= max_items_per_category:
            continue
        payload = _public_payload(model.payload or {})
        key = str(payload.get("key", "") or "").strip()
        source_type = str(model.source_type or "").strip()
        detail = _compact_reference_detail(payload)
        line = f"- {model.name}"
        meta_parts = [part for part in (source_type, key) if part]
        if meta_parts:
            line += f" ({', '.join(meta_parts)})"
        if detail:
            line += f": {detail}"
        grouped[category].append(line)

    sections: list[str] = []
    total_chars = 0
    for category in allowed_categories:
        items = grouped.get(category, [])
        if not items:
            continue
        section = f"{REFERENCE_CONTEXT_TITLES.get(category, category.title())}:\n" + "\n".join(items)
        projected = total_chars + len(section) + (2 if sections else 0)
        if sections and projected > max_total_chars:
            break
        if not sections and len(section) > max_total_chars:
            return section[:max_total_chars].rstrip()
        sections.append(section)
        total_chars = projected
    return "\n\n".join(sections)


_SYMPTOM_STOP_WORDS: frozenset[str] = frozenset({
    "рекомендации", "одинарные", "смеси", "питательные добавки",
    "рекомендуемые", "способы применения", "применение",
})


def _extract_ru_name(raw: str) -> str:
    """Extract Russian name from 'English (Russian)' pattern, or return cleaned raw."""
    # First strip any sentence continuation (text after '. Capital')
    clean = re.split(r"\.\s+[A-ZА-Я]", raw)[0].strip()
    # Extract content in parentheses as Russian name
    m = re.search(r"\(([^)]+)\)", clean)
    if m:
        return " ".join(m.group(1).split())  # normalize spaces
    return " ".join(clean.split())


def _resolve_symptom_refs(
    raw_names: list[str],
    name_to_slug: dict[str, str],
    slug_to_ru: dict[str, str],
) -> tuple[list[str], list[str]]:
    """Filter stop-words/artifacts from symptom oil/blend names, resolve to RU names + slugs."""
    result_names: list[str] = []
    result_slugs: list[str] = []
    seen_slugs: set[str] = set()
    for raw in raw_names:
        name = str(raw).strip()
        if not name:
            continue
        if name.lower() in _SYMPTOM_STOP_WORDS:
            continue
        if len(name) > 60:
            continue
        if name.startswith(("•", ".", "-", "·")):
            continue
        # Extract Russian name from "English (Russian)" pattern if present
        ru_from_parens = _extract_ru_name(name) if "(" in name else ""
        # Try to find slug using both the extracted RU name and the raw name
        slug = (
            name_to_slug.get(_normalize(ru_from_parens)) if ru_from_parens else None
        ) or name_to_slug.get(_normalize(name)) or ""
        # Deduplicate by slug
        if slug and slug in seen_slugs:
            continue
        if slug:
            seen_slugs.add(slug)
        # Prefer stored Russian name from aroma DB over extracted
        display_name = slug_to_ru.get(slug, "") if slug else ""
        if not display_name:
            display_name = ru_from_parens or name
        result_names.append(display_name)
        result_slugs.append(slug)
    return result_names, result_slugs


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

    aroma_slug_to_name: dict[str, str] = {m.slug: m.name for m in aroma_models}
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
        if name.startswith(("•", ".", "-", "·")):
            continue
        slug = stored_oil_slugs[i] if i < len(stored_oil_slugs) else ""
        if slug and slug in seen:
            continue
        if slug:
            seen.add(slug)
        # Prefer Russian name from aroma DB; fall back to extracted/raw name
        db_display = aroma_slug_to_name.get(slug, "") if slug else ""
        # Validate DB name is not a garbage artifact (starts with bullet/dot/etc.)
        if db_display and not db_display.startswith(("•", ".", "-", "·")):
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
        if name.startswith(("•", ".", "-", "·")):
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
        # Build lookup: normalised name/alias → slug
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


async def get_reference_card(category: str, slug_or_name: str) -> dict[str, object] | None:
    await seed_reference_cards_if_empty()
    key = _normalize(slug_or_name)
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(AromaCardModel).where(AromaCardModel.category == category))
        models = result.scalars().all()
    for model in models:
        aliases = [_normalize(alias) for alias in (model.aliases or [])]
        if model.slug == slug_or_name or _normalize(model.name) == key or key in aliases:
            serialized = _serialize_model(model)
            if category == "aroma":
                serialized = await _enrich_aroma_cross_refs(serialized)
            elif category == "symptom":
                serialized = await _enrich_symptom_cross_refs(serialized)
            elif category == "blend":
                serialized = await _enrich_blend_cross_refs(serialized)
            return serialized
    return None


async def update_reference_card(category: str, slug: str, payload: dict[str, object]) -> dict[str, object] | None:
    await seed_reference_cards_if_empty()
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AromaCardModel).where(AromaCardModel.category == category, AromaCardModel.slug == slug)
        )
        model = result.scalar_one_or_none()
        if not model:
            return None
        stored_payload = dict(model.payload or {})
        current = _public_payload(stored_payload)
        seed_payload = dict(stored_payload.get(INTERNAL_SEED_KEY) or current)
        manual_overrides = set(stored_payload.get(INTERNAL_OVERRIDES_KEY, []))
        resource_values = payload.get("resource_values", {})
        if not isinstance(resource_values, dict):
            resource_values = {}
        current.update(
            {
                "description": str(payload.get("description", current.get("description", ""))).strip(),
                "questions": str(payload.get("questions", current.get("questions", ""))).strip(),
                "nps_effect": str(payload.get("nps_effect", current.get("nps_effect", ""))).strip(),
                "therapeutic_properties": str(payload.get("therapeutic_properties", current.get("therapeutic_properties", ""))).strip(),
                "psychological_properties": str(payload.get("psychological_properties", current.get("psychological_properties", ""))).strip(),
                "history": str(payload.get("history", current.get("history", ""))).strip(),
                "volatility": str(payload.get("volatility", current.get("volatility", ""))).strip(),
                "botanical_family": str(payload.get("botanical_family", current.get("botanical_family", ""))).strip(),
                "origin_countries": str(payload.get("origin_countries", current.get("origin_countries", ""))).strip(),
                "extraction_method": str(payload.get("extraction_method", current.get("extraction_method", ""))).strip(),
                "key": str(payload.get("key", current.get("key", ""))).strip(),
                "resource_values": {
                    "plus": str(resource_values.get("plus", current.get("resource_values", {}).get("plus", ""))).strip(),
                    "minus": str(resource_values.get("minus", current.get("resource_values", {}).get("minus", ""))).strip(),
                },
            }
        )
        for field in EDITABLE_FIELDS:
            if current.get(field, "") == seed_payload.get(field, ""):
                manual_overrides.discard(field)
            else:
                manual_overrides.add(field)

        seed_resources = dict(seed_payload.get("resource_values", {}) or {})
        current_resources = dict(current.get("resource_values", {}) or {})
        for field in RESOURCE_FIELDS:
            path = f"resource_values.{field}"
            if current_resources.get(field, "") == seed_resources.get(field, ""):
                manual_overrides.discard(path)
            else:
                manual_overrides.add(path)

        current[INTERNAL_SEED_KEY] = seed_payload
        current[INTERNAL_OVERRIDES_KEY] = sorted(manual_overrides)
        model.payload = current
        model.updated_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(model)
        return _serialize_model(model)


async def enrich_reference_card(category: str, slug: str) -> dict[str, object] | None:
    card = await get_reference_card(category, slug)
    if not card:
        return None
    enriched = enrich_reference_card_sync(category, card)
    return await update_reference_card(category, slug, enriched)
