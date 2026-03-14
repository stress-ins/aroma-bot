#!/usr/bin/env python3
"""Normalize ALL CAPS card names in the database.

Usage:
    .venv/bin/python scripts/fix_card_name_casing.py [--dry-run]

Fixes KB-002: 161 symptoms have ALL CAPS names, 2 aroma cards have garbage names,
1 blend has ALL CAPS name_ru.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Manual overrides for specific cards with garbage names
MANUAL_FIXES: dict[str, dict] = {
    "hong-kuai": {
        "name": "Хон Куай",
        "payload_name_ru": "Хон Куай",
    },
    "laurus": {
        "name": "Лавр",
        "payload_name_ru": "Лавр",
    },
    "blend-sara": {
        "payload_name_ru": "Сара",
    },
}


def normalize_caps(name: str) -> str:
    """Convert ALL CAPS name to sentence case.

    'АЛЛЕРГИЧЕСКИЙ РИНИТ' → 'Аллергический ринит'
    'ЖАР / ВЫСОКАЯ ТЕМПЕРАТУРА' → 'Жар / высокая температура'
    Short names (≤3 chars) are left as-is.
    """
    if len(name) <= 3:
        return name
    if name != name.upper():
        return name
    return name.capitalize()


async def run(dry_run: bool = False) -> None:
    from sqlalchemy import select
    from db.session import AsyncSessionLocal, init_db
    from db.models import AromaCardModel

    await init_db()

    fixed = 0
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(AromaCardModel))
        cards = result.scalars().all()

        for card in cards:
            changes: list[str] = []
            slug = card.slug

            # Manual fixes for garbage names
            if slug in MANUAL_FIXES:
                fix = MANUAL_FIXES[slug]
                if "name" in fix and card.name != fix["name"]:
                    changes.append(f"name: {card.name!r} → {fix['name']!r}")
                    if not dry_run:
                        card.name = fix["name"]
                if "payload_name_ru" in fix:
                    payload = dict(card.payload) if card.payload else {}
                    old_nr = payload.get("name_ru", "")
                    if old_nr != fix["payload_name_ru"]:
                        changes.append(f"payload.name_ru: {old_nr!r} → {fix['payload_name_ru']!r}")
                        if not dry_run:
                            payload["name_ru"] = fix["payload_name_ru"]
                            card.payload = payload

            # Normalize ALL CAPS names
            else:
                new_name = normalize_caps(card.name)
                if new_name != card.name:
                    changes.append(f"name: {card.name!r} → {new_name!r}")
                    if not dry_run:
                        card.name = new_name

                # Normalize payload.name_ru
                payload = dict(card.payload) if card.payload else {}
                name_ru = payload.get("name_ru", "")
                if name_ru:
                    new_name_ru = normalize_caps(name_ru)
                    if new_name_ru != name_ru:
                        changes.append(f"payload.name_ru: {name_ru!r} → {new_name_ru!r}")
                        if not dry_run:
                            payload["name_ru"] = new_name_ru
                            card.payload = payload

            if changes:
                fixed += 1
                prefix = "[DRY-RUN] " if dry_run else ""
                print(f"{prefix}{slug}: {'; '.join(changes)}")

        if not dry_run:
            await session.commit()

    print(f"\n{'Would fix' if dry_run else 'Fixed'}: {fixed} cards")


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize ALL CAPS card names")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
