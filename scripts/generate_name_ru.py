#!/usr/bin/env python3
"""Phase 3: Generate Russian names (name_ru) for aromas that lack them.

Usage:
    .venv/bin/python scripts/generate_name_ru.py --dry-run
    .venv/bin/python scripts/generate_name_ru.py
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Well-known translations — skip API calls for these
KNOWN_TRANSLATIONS = {
    "myrrh": "Мирра",
    "orange": "Апельсин",
    "basil": "Базилик",
    "bergamot": "Бергамот",
    "helichrysum": "Бессмертник",
    "geranium": "Герань",
    "grapefruit": "Грейпфрут",
    "spruce": "Ель",
    "ylang-ylang": "Иланг-иланг",
    "cassia": "Кассия",
    "cedarwood": "Кедр",
    "frankincense": "Ладан",
    "lemon": "Лимон",
    "marjoram": "Майоран",
    "mandarin": "Мандарин",
    "juniper": "Можжевельник",
    "clary-sage": "Шалфей мускатный",
    "neroli": "Нероли",
    "oregano": "Орегано",
    "sandalwood": "Сандал",
    "black-pepper": "Чёрный перец",
    "ho-wood": "Хо дерево",
    "bay-laurel": "Лавр благородный",
    "pink-pepper": "Розовый перец",
    "fragonia": "Фрагония",
    "black-spruce": "Чёрная ель",
    "blue-spruce": "Голубая ель",
    "vetiver": "Ветивер",
    "jasmine": "Жасмин",
    "rose": "Роза",
    "lavender": "Лаванда",
    "patchouli": "Пачули",
    "peppermint": "Мята перечная",
    "tea-tree": "Чайное дерево",
    "eucalyptus": "Эвкалипт",
    "rosemary": "Розмарин",
    "thyme": "Тимьян",
    "cypress": "Кипарис",
    "ginger": "Имбирь",
    "cinnamon": "Корица",
    "clove": "Гвоздика",
    "fennel": "Фенхель",
    "kunzea": "Кунцея",
    "benzoin": "Бензоин",
    "blue-tansy": "Голубая пижма",
    "caraway": "Тмин",
    "carrot-seed": "Морковное семя",
    "cistus": "Ладанник",
    "hyssop": "Иссоп",
    "manuka": "Манука",
    "petitgrain": "Петитгрейн",
    "laurus": "Лавр",
    "copaiba": "Копайба",
    "wintergreen": "Грушанка",
}


async def run(dry_run: bool = False) -> None:
    import anthropic
    from sqlalchemy import select
    from db.session import AsyncSessionLocal
    from db.models import AromaCardModel
    from config import settings

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AromaCardModel).where(AromaCardModel.category == "aroma")
        )
        cards = result.scalars().all()

        updated = 0
        skipped = 0

        for card in cards:
            payload = dict(card.payload or {})
            name_ru = str(payload.get("name_ru", "")).strip()
            if name_ru:
                skipped += 1
                continue

            slug = card.slug
            name = card.name

            # Try known translations first
            if slug in KNOWN_TRANSLATIONS:
                ru = KNOWN_TRANSLATIONS[slug]
                print(f"  {slug}: '{name}' → {ru} (dict)")
            elif name.lower() in KNOWN_TRANSLATIONS:
                ru = KNOWN_TRANSLATIONS[name.lower()]
                print(f"  {slug}: '{name}' → {ru} (dict)")
            else:
                if not settings.anthropic_api_key:
                    print(f"  {slug}: '{name}' → SKIP (no API key)")
                    continue
                if dry_run:
                    print(f"  {slug}: '{name}' → [dry run] would call Claude")
                    updated += 1
                    continue
                client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
                response = client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=50,
                    messages=[{
                        "role": "user",
                        "content": (
                            f"Переведи название эфирного масла на русский: \"{name}\". "
                            "Ответь только русским названием, без пояснений."
                        ),
                    }],
                )
                ru = response.content[0].text.strip().strip('"').strip("«»")
                print(f"  {slug}: '{name}' → {ru} (Claude)")
                time.sleep(0.5)

            if not dry_run:
                payload["name_ru"] = ru
                card.payload = payload
                card.updated_at = datetime.now(timezone.utc)
            updated += 1

        if not dry_run:
            await session.commit()

        print(f"\nDone: {updated} updated, {skipped} already had name_ru")
        if dry_run:
            print("[DRY RUN]")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run))
