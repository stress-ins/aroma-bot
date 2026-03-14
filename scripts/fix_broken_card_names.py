#!/usr/bin/env python3
"""Fix broken card names and remove junk entries from aroma_cards.

Usage:
    .venv/bin/python scripts/fix_broken_card_names.py [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Cards with broken name_ru / name fields
NAME_FIXES = {
    "davana": {"name": "Давана", "name_ru": "Давана"},
    "laurus": {"name": "Лавр", "name_ru": "Лавр"},
}

# Junk cards to delete entirely
DELETE_SLUGS = [
    "symptom-ладана-frankincense",
    "symptom-обратитесь-к-врачу",
    "symptom-окотею-ocotea",
    "symptom-одинарные",
    "symptom-альцгеимера",
    "symptom-смесь-от-морщин",
    "blend-no-ru",  # duplicate of Harmony
]


async def run(dry_run: bool = False) -> None:
    from sqlalchemy import select, delete
    from db.session import AsyncSessionLocal
    from db.models import AromaCardModel

    async with AsyncSessionLocal() as session:
        # Fix broken names
        for slug, fixes in NAME_FIXES.items():
            result = await session.execute(
                select(AromaCardModel).where(AromaCardModel.slug == slug)
            )
            card = result.scalar_one_or_none()
            if not card:
                print(f"SKIP: {slug} not found")
                continue
            print(f"FIX: {slug} — name '{card.name}' → '{fixes['name']}'")
            if not dry_run:
                card.name = fixes["name"]
                payload = dict(card.payload or {})
                payload["name_ru"] = fixes["name_ru"]
                card.payload = payload
                card.updated_at = datetime.now(timezone.utc)

        # Delete junk cards
        for slug in DELETE_SLUGS:
            result = await session.execute(
                select(AromaCardModel).where(AromaCardModel.slug == slug)
            )
            card = result.scalar_one_or_none()
            if not card:
                print(f"SKIP: {slug} not found (already deleted)")
                continue
            print(f"DELETE: {slug} ({card.category}: {card.name})")
            if not dry_run:
                await session.delete(card)

        if not dry_run:
            await session.commit()
            print("Done — changes committed.")
        else:
            print("Dry run — no changes written.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fix broken card names")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run))
