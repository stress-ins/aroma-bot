#!/usr/bin/env python3
"""
Fill missing descriptions for AromaCards using Claude.

Usage:
    .venv/bin/python scripts/fill_missing_descriptions.py [--dry-run] [--category aroma]

Targets cards where payload.description is missing or shorter than 20 characters.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from db.models import AromaCardModel
from db.session import AsyncSessionLocal, init_db

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


DESCRIPTION_PROMPT = """\
Ты — эксперт по ароматерапии и сенсорным практикам.
Напиши краткое описание (2-3 предложения, до 200 символов) для следующей карточки.
Пиши на русском языке, профессионально, без лишних слов.
Упомяни ключевые свойства и применение.

Категория: {category}
Название: {name}
Псевдоним: {slug}
Дополнительные данные: {extra}

Верни ТОЛЬКО текст описания без кавычек и меток.
"""


def _call_claude(prompt: str) -> str:
    import anthropic
    from config import settings

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


def _needs_description(card: AromaCardModel) -> bool:
    description = card.payload.get("description", "") if card.payload else ""
    return not description or len(str(description).strip()) < 20


def _build_extra(card: AromaCardModel) -> str:
    payload = card.payload or {}
    parts = []
    for field in ("therapeutic_properties", "psychological_properties", "botanical_family", "key"):
        val = payload.get(field)
        if val:
            parts.append(f"{field}: {str(val)[:100]}")
    return "; ".join(parts) if parts else "нет"


async def run(dry_run: bool, category: str | None) -> None:
    await init_db()

    async with AsyncSessionLocal() as session:
        query = select(AromaCardModel)
        if category:
            query = query.where(AromaCardModel.category == category)
        result = await session.execute(query)
        cards = result.scalars().all()

    targets = [c for c in cards if _needs_description(c)]
    logger.info("Found %d cards needing description (total scanned: %d)", len(targets), len(cards))

    if dry_run:
        for card in targets:
            logger.info("  [DRY-RUN] Would fill: %s (%s)", card.slug, card.category)
        return

    from config import settings
    if not settings.anthropic_api_key:
        logger.error("ANTHROPIC_API_KEY not set — cannot generate descriptions")
        sys.exit(1)

    updated = 0
    errors = 0
    for card in targets:
        try:
            extra = _build_extra(card)
            prompt = DESCRIPTION_PROMPT.format(
                category=card.category,
                name=card.name,
                slug=card.slug,
                extra=extra,
            )
            description = _call_claude(prompt)
            logger.info("  %s — generated: %s", card.slug, description[:80])

            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(AromaCardModel).where(AromaCardModel.id == card.id)
                )
                fresh = result.scalar_one_or_none()
                if fresh:
                    payload = dict(fresh.payload or {})
                    payload["description"] = description
                    fresh.payload = payload
                    await session.commit()
            updated += 1
        except Exception as exc:
            logger.error("  Error filling %s: %s", card.slug, exc)
            errors += 1

    logger.info("Done. Updated: %d, Errors: %d", updated, errors)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fill missing AromaCard descriptions")
    parser.add_argument("--dry-run", action="store_true", help="Show which cards would be updated")
    parser.add_argument("--category", help="Filter by category (aroma/practice/sound/etc)")
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run, category=args.category))


if __name__ == "__main__":
    main()
