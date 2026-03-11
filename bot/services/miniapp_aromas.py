from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from sqlalchemy import select

from db.models import AromaCardModel
from db.session import AsyncSessionLocal


BASE_DIR = Path(__file__).resolve().parents[2]
SEED_FILE = BASE_DIR / "data" / "aroma_cards_seed.json"


def _normalize(value: str) -> str:
    return " ".join(value.lower().replace("ё", "е").replace('"', "").split())


def _source_image(source_type: str, title: str) -> str:
    palette = {
        "citrus": ("#f6a623", "#ffe3a1", "цитрус"),
        "flower": ("#d36a8b", "#f6d5de", "цветок"),
        "tree": ("#5e7d3a", "#d7e5b8", "дерево"),
        "resin": ("#8a5a3c", "#e4c9b0", "смола"),
        "spice": ("#b56134", "#f0cfb8", "специя"),
        "herb": ("#5d8c63", "#d7edd9", "трава"),
        "grass": ("#4f8b57", "#d4ecd7", "трава"),
    }
    primary, secondary, label = palette.get(source_type, palette["herb"])
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
      <text x='54' y='196' font-size='46' font-family='Arial' font-weight='700' fill='#2d241e'>{title}</text>
      <text x='54' y='244' font-size='22' font-family='Arial' fill='#6a5a4a'>Источник сырья для эфирного масла</text>
      <path d='M470 286c-45-79-133-118-219-98 61 8 120 44 159 99H220v37h248c31 0 41-20 34-38l-32-70Z' fill='{primary}' fill-opacity='0.8' />
    </svg>
    """.strip()
    return f"data:image/svg+xml;charset=UTF-8,{quote(svg)}"


def _serialize_model(model: AromaCardModel) -> dict[str, object]:
    payload = dict(model.payload or {})
    payload.setdefault("resource_values", {"plus": "", "minus": ""})
    payload["slug"] = model.slug
    payload["name"] = model.name
    payload["aliases"] = list(model.aliases or [])
    payload["source_type"] = model.source_type
    payload["image_url"] = _source_image(model.source_type, model.name)
    payload["image_alt"] = f"{model.name}: источник сырья"
    payload["updated_at"] = model.updated_at.isoformat() if isinstance(model.updated_at, datetime) else str(model.updated_at)
    return payload


def _summary(model: AromaCardModel) -> dict[str, str]:
    payload = dict(model.payload or {})
    return {
        "slug": model.slug,
        "name": model.name,
        "description": str(payload.get("description", "")),
    }


async def seed_aroma_cards_if_empty() -> None:
    if not SEED_FILE.exists():
        return
    async with AsyncSessionLocal() as session:
        existing = await session.execute(select(AromaCardModel.id).limit(1))
        if existing.first():
            return
        raw_items = json.loads(SEED_FILE.read_text(encoding="utf-8"))
        now = datetime.now(timezone.utc)
        for item in raw_items:
            session.add(
                AromaCardModel(
                    slug=str(item["slug"]),
                    name=str(item["name"]),
                    source_type=str(item.get("source_type", "herb")),
                    aliases=list(item.get("aliases", [])),
                    payload=dict(item),
                    created_at=now,
                    updated_at=now,
                )
            )
        await session.commit()


async def list_aromas() -> list[dict[str, str]]:
    await seed_aroma_cards_if_empty()
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(AromaCardModel))
        models = result.scalars().all()
    models = sorted(models, key=lambda item: _normalize(item.name))
    return [_summary(model) for model in models]


async def get_aroma_card(slug_or_name: str) -> dict[str, object] | None:
    await seed_aroma_cards_if_empty()
    key = _normalize(slug_or_name)
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(AromaCardModel))
        models = result.scalars().all()
    for model in models:
        aliases = [_normalize(alias) for alias in (model.aliases or [])]
        if model.slug == slug_or_name or _normalize(model.name) == key or key in aliases:
            return _serialize_model(model)
    return None


async def update_aroma_card(slug: str, payload: dict[str, object]) -> dict[str, object] | None:
    await seed_aroma_cards_if_empty()
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(AromaCardModel).where(AromaCardModel.slug == slug))
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


async def replace_aroma_cards(seed_items: list[dict[str, object]]) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(AromaCardModel.__table__.delete())
        now = datetime.now(timezone.utc)
        for item in seed_items:
            session.add(
                AromaCardModel(
                    slug=str(item["slug"]),
                    name=str(item["name"]),
                    source_type=str(item.get("source_type", "herb")),
                    aliases=list(item.get("aliases", [])),
                    payload=dict(item),
                    created_at=now,
                    updated_at=now,
                )
            )
        await session.commit()
