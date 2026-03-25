#!/usr/bin/env python3
"""Import crystal therapy and sound healing cards from seed JSON into the database.

Usage:
    .venv/bin/python scripts/seed_crystals.py --dry-run       # preview
    .venv/bin/python scripts/seed_crystals.py --limit 5       # first 5
    .venv/bin/python scripts/seed_crystals.py                 # full import
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CRYSTAL_SEED_PATH = ROOT / "data" / "crystal_cards_seed.json"
SOUND_SEED_PATH = ROOT / "data" / "sound_healing_seed.json"

logger = logging.getLogger(__name__)


async def seed_crystals(dry_run: bool = False, limit: int | None = None) -> tuple[int, int]:
    """Load crystal cards from seed JSON into DB. Idempotent -- skips existing slugs."""
    return await _seed_from_file(CRYSTAL_SEED_PATH, dry_run=dry_run, limit=limit)


async def seed_sound_healing(dry_run: bool = False, limit: int | None = None) -> tuple[int, int]:
    """Load sound healing cards from seed JSON into DB. Idempotent -- skips existing slugs."""
    return await _seed_from_file(SOUND_SEED_PATH, dry_run=dry_run, limit=limit)


async def _seed_from_file(
    path: Path, *, dry_run: bool = False, limit: int | None = None
) -> tuple[int, int]:
    """Generic loader: reads a JSON array of card dicts and upserts into AromaCardModel.

    Returns (inserted, updated) counts.
    """
    from sqlalchemy import select

    from db.models import AromaCardModel
    from db.session import AsyncSessionLocal

    if not path.exists():
        logger.warning("Seed file not found: %s", path)
        return 0, 0

    cards = json.loads(path.read_text(encoding="utf-8"))
    if limit:
        cards = cards[:limit]

    inserted = 0
    updated = 0

    async with AsyncSessionLocal() as session:
        for card in cards:
            slug = card["slug"]
            result = await session.execute(
                select(AromaCardModel).where(AromaCardModel.slug == slug)
            )
            existing = result.scalar_one_or_none()

            if existing:
                print(f"  UPDATE {slug}")
                if not dry_run:
                    # Merge payload without overwriting non-empty fields
                    old_payload = dict(existing.payload or {})
                    for key, value in card["payload"].items():
                        old_val = old_payload.get(key)
                        if old_val is None or old_val == "" or old_val == []:
                            old_payload[key] = value
                    existing.payload = old_payload
                    existing.updated_at = datetime.now(timezone.utc)
                updated += 1
            else:
                print(f"  INSERT {slug}")
                if not dry_run:
                    session.add(
                        AromaCardModel(
                            slug=slug,
                            name=card["name"],
                            category=card["category"],
                            source_type=card["source_type"],
                            aliases=card.get("aliases", []),
                            payload=card["payload"],
                        )
                    )
                inserted += 1

        if not dry_run:
            await session.commit()

    return inserted, updated


async def run(dry_run: bool = False, limit: int | None = None) -> None:
    print("=== Seeding crystal therapy cards ===")
    c_ins, c_upd = await seed_crystals(dry_run=dry_run, limit=limit)
    action = "Would insert" if dry_run else "Inserted"
    print(f"\n{action} {c_ins}, updated {c_upd} crystal cards")

    print("\n=== Seeding sound healing cards ===")
    s_ins, s_upd = await seed_sound_healing(dry_run=dry_run, limit=limit)
    print(f"\n{action} {s_ins}, updated {s_upd} sound healing cards")

    total = c_ins + c_upd + s_ins + s_upd
    print(f"\nTotal: {total} cards processed.")
    if dry_run:
        print("Dry run -- no changes written.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Seed crystal & sound healing cards into DB")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None, help="Import only first N cards per category")
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run, limit=args.limit))
