#!/usr/bin/env python3
"""Import osteopractice and biodynamics cards from seed JSON into the database.

Usage:
    .venv/bin/python scripts/seed_bodywork.py --dry-run
    .venv/bin/python scripts/seed_bodywork.py
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OSTEO_SEED_PATH = ROOT / "data" / "osteo_seed.json"
BIODYNAMICS_SEED_PATH = ROOT / "data" / "biodynamics_seed.json"

logger = logging.getLogger(__name__)


async def run(dry_run: bool = False, limit: int | None = None) -> None:
    from scripts.seed_crystals import _seed_from_file

    print("=== Seeding osteopractice cards ===")
    o_ins, o_upd = await _seed_from_file(OSTEO_SEED_PATH, dry_run=dry_run, limit=limit)
    action = "Would insert" if dry_run else "Inserted"
    print(f"\n{action} {o_ins}, updated {o_upd} osteo cards")

    print("\n=== Seeding biodynamics cards ===")
    b_ins, b_upd = await _seed_from_file(BIODYNAMICS_SEED_PATH, dry_run=dry_run, limit=limit)
    print(f"\n{action} {b_ins}, updated {b_upd} biodynamics cards")

    total = o_ins + o_upd + b_ins + b_upd
    print(f"\nTotal: {total} cards processed.")
    if dry_run:
        print("Dry run -- no changes written.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Seed osteo & biodynamics cards into DB")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run, limit=args.limit))
