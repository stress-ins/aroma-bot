#!/usr/bin/env python3
"""Import massage cards from seed JSON into the database.

Usage:
    .venv/bin/python scripts/seed_massage.py --dry-run       # preview
    .venv/bin/python scripts/seed_massage.py                 # full import
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

MASSAGE_SEED_PATH = ROOT / "data" / "massage_seed.json"

logger = logging.getLogger(__name__)


async def run(dry_run: bool = False, limit: int | None = None) -> None:
    # Reuse the generic loader from seed_crystals
    from scripts.seed_crystals import _seed_from_file

    print("=== Seeding massage cards ===")
    ins, upd = await _seed_from_file(MASSAGE_SEED_PATH, dry_run=dry_run, limit=limit)
    action = "Would insert" if dry_run else "Inserted"
    print(f"\n{action} {ins}, updated {upd} massage cards")
    if dry_run:
        print("Dry run -- no changes written.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Seed massage cards into DB")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run, limit=args.limit))
