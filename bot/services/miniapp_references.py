from __future__ import annotations

import json
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
REFERENCE_CATEGORIES = {"aroma", "practice", "sound"}
REFERENCE_IMAGES_DIR = BASE_DIR / "assets" / "reference_images"
SHARED_IMAGE_OVERRIDES = {
    ("practice", "breath"): "nature.jpg",
    ("practice", "meditation"): "nature.jpg",
    ("practice", "body"): "nature.jpg",
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
        "sound": "источник звука",
    }.get(category, "справочник")


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
        "sound": ("#5468b8", "#dbe1fb", "звук"),
        "instrument": ("#8b6e4a", "#eadcc9", "инструмент"),
        "voice": ("#ad5f9e", "#f0d7eb", "голос"),
    }
    primary, secondary, label = palette.get(source_type, palette["herb"])
    card_label = _image_label(category)
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
      <text x='54' y='196' font-size='42' font-family='Arial' font-weight='700' fill='#2d241e'>{title}</text>
      <text x='54' y='244' font-size='22' font-family='Arial' fill='#6a5a4a'>{card_label}</text>
      <path d='M470 286c-45-79-133-118-219-98 61 8 120 44 159 99H220v37h248c31 0 41-20 34-38l-32-70Z' fill='{primary}' fill-opacity='0.8' />
    </svg>
    """.strip()
    return f"data:image/svg+xml;charset=UTF-8,{quote(svg)}"


def _serialize_model(model: AromaCardModel) -> dict[str, object]:
    payload = dict(model.payload or {})
    payload.setdefault("resource_values", {"plus": "", "minus": ""})
    payload["slug"] = model.slug
    payload["name"] = model.name
    payload["category"] = model.category
    payload["aliases"] = list(model.aliases or [])
    payload["source_type"] = model.source_type
    payload["image_url"] = (
        _local_reference_image_url(model.category, model.slug)
        or _shared_reference_image_url(model.category, model.slug, model.source_type)
        or _source_image(model.source_type, model.name, model.category)
    )
    payload["image_alt"] = f"{model.name}: {_image_label(model.category)}"
    return payload


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
            category = str(item.get("category", "aroma"))
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
                if dict(existing.payload or {}) != payload:
                    existing.payload = payload
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
                    payload=payload,
                    created_at=now,
                    updated_at=now,
                )
            )
        await session.commit()


async def list_reference_cards(category: str) -> list[dict[str, str]]:
    await seed_reference_cards_if_empty()
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(AromaCardModel).where(AromaCardModel.category == category))
        models = result.scalars().all()
    models = sorted(models, key=lambda item: _normalize(item.name))
    return [
        {
            "slug": model.slug,
            "name": model.name,
            "description": str((model.payload or {}).get("description", "")),
            "category": model.category,
        }
        for model in models
    ]


async def get_reference_card(category: str, slug_or_name: str) -> dict[str, object] | None:
    await seed_reference_cards_if_empty()
    key = _normalize(slug_or_name)
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(AromaCardModel).where(AromaCardModel.category == category))
        models = result.scalars().all()
    for model in models:
        aliases = [_normalize(alias) for alias in (model.aliases or [])]
        if model.slug == slug_or_name or _normalize(model.name) == key or key in aliases:
            return _serialize_model(model)
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
        current = dict(model.payload or {})
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
