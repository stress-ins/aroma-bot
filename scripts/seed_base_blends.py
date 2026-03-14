#!/usr/bin/env python3
"""Import blend cards from data/base_blends.json into the database.

Usage:
    .venv/bin/python scripts/seed_base_blends.py --dry-run       # preview
    .venv/bin/python scripts/seed_base_blends.py --limit 5       # first 5
    .venv/bin/python scripts/seed_base_blends.py                 # full import
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

JSON_PATH = ROOT / "data" / "base_blends.json"


def _deep_merge_patch(existing: dict, patch: dict) -> dict:
    """Merge patch into existing without overwriting non-empty fields."""
    merged = dict(existing)
    for key, value in patch.items():
        old = merged.get(key)
        if old is None or old == "" or old == []:
            merged[key] = value
        elif isinstance(old, dict) and isinstance(value, dict):
            merged[key] = _deep_merge_patch(old, value)
        elif isinstance(old, list) and isinstance(value, list) and len(value) > len(old):
            merged[key] = value
        elif key in ("description", "category_group") and value:
            # Always update description and category_group
            merged[key] = value
    return merged


async def run(dry_run: bool = False, limit: int | None = None) -> None:
    from sqlalchemy import select
    from db.session import AsyncSessionLocal
    from db.models import AromaCardModel

    blends = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    if limit:
        blends = blends[:limit]

    inserted = 0
    updated = 0

    async with AsyncSessionLocal() as session:
        for card in blends:
            slug = card["slug"]
            result = await session.execute(
                select(AromaCardModel).where(AromaCardModel.slug == slug)
            )
            existing = result.scalar_one_or_none()

            if existing:
                print(f"  UPDATE {slug}")
                if not dry_run:
                    existing.payload = _deep_merge_patch(
                        dict(existing.payload or {}), card["payload"],
                    )
                    existing.updated_at = datetime.now(timezone.utc)
                updated += 1
            else:
                print(f"  INSERT {slug}")
                if not dry_run:
                    session.add(AromaCardModel(
                        slug=slug,
                        name=card["name"],
                        category=card["category"],
                        source_type=card["source_type"],
                        aliases=card.get("aliases", []),
                        payload=card["payload"],
                    ))
                inserted += 1

        if not dry_run:
            await session.commit()

    action = "Would insert" if dry_run else "Inserted"
    print(f"\n{action} {inserted}, updated {updated} (total {inserted + updated} blends)")
    if dry_run:
        print("Dry run — no changes written.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed base blends into DB")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None, help="Import only first N blends")
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run, limit=args.limit))
