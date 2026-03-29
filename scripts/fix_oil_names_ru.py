"""One-time script: fix model.name for PDF-import aroma cards.

For cards where model.name is in English (e.g. "Blue Tansy"),
replace it with payload.name_ru (e.g. "Голубая пижма").

Idempotent: skips cards where name already contains Cyrillic.
Run: .venv/bin/python scripts/fix_oil_names_ru.py [--dry-run]
"""
from __future__ import annotations

import asyncio
import logging
import re
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select

from db.models import AromaCardModel
from db.session import AsyncSessionLocal

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

# Fallback mapping for cards without name_ru in payload
SLUG_TO_RU: dict[str, str] = {
    "angelica": "Ангелика",
    "blue-tansy": "Голубая пижма",
    "caraway": "Тмин",
    "carrot-seed": "Морковное семя",
    "cistus": "Цистус (Ладанник)",
    "davana": "Давана",
    "dill": "Укроп",
    "elemi": "Элеми",
    "eucaliptus-blue": "Эвкалипт голубой",
    "hong-kuai": "Хун Куай",
    "laurus": "Лавр",
    "ledum": "Багульник",
    "manuka": "Манука",
    "melissa": "Мелисса",
    "myrtle": "Мирт",
    "palmarosa": "Пальмароза",
    "palo-santo": "Пало Санто",
    "petitgrain": "Петитгрейн",
    "ravintsara": "Равинтсара",
    "roman-chamomile": "Римская ромашка",
    "sacred-frankincense": "Священный ладан",
    "spearmint": "Мята колосовая",
    "valerian": "Валериана",
    "wintergreen": "Винтергрин",
}

_CYRILLIC_RE = re.compile(r"[а-яА-ЯёЁ]")


def _has_cyrillic(text: str) -> bool:
    return bool(_CYRILLIC_RE.search(text))


async def main() -> None:
    dry_run = "--dry-run" in sys.argv
    updated = 0
    skipped = 0

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AromaCardModel).where(AromaCardModel.category == "aroma")
        )
        cards = result.scalars().all()

        for card in cards:
            # Skip cards that already have Cyrillic name
            if _has_cyrillic(card.name):
                skipped += 1
                continue

            # Try to get Russian name from payload, then fallback map
            payload = card.payload or {}
            name_ru = (payload.get("name_ru") or "").strip()
            if not name_ru:
                name_ru = SLUG_TO_RU.get(card.slug, "")

            if not name_ru:
                log.warning("  SKIP %s: no Russian name available (current: %s)", card.slug, card.name)
                skipped += 1
                continue

            log.info("  FIX  %s: '%s' -> '%s'", card.slug, card.name, name_ru)
            if not dry_run:
                card.name = name_ru
                # Also ensure payload.name_ru is set
                if not payload.get("name_ru"):
                    p = dict(payload)
                    p["name_ru"] = name_ru
                    card.payload = p
            updated += 1

        if updated > 0 and not dry_run:
            await session.commit()
            log.info("Committed %d updates", updated)

    mode = " (DRY RUN)" if dry_run else ""
    log.info("Done%s: %d updated, %d skipped", mode, updated, skipped)


if __name__ == "__main__":
    asyncio.run(main())
