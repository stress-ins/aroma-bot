"""Apply parent_group hierarchy to existing symptom cards in DB.

Reads the parsed PDF symptom data (data/pdf_symptoms.json) and upserts
parent_group + category_group into each matching symptom card payload.

Usage:
    .venv/bin/python scripts/reseed_symptom_hierarchy.py [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SYMPTOMS_FILE = ROOT / "data" / "pdf_symptoms.json"


async def run(dry_run: bool = False) -> int:
    if not SYMPTOMS_FILE.exists():
        print(f"ERROR: {SYMPTOMS_FILE} not found. Run parse_handbook_pdf.py first.")
        return 0

    items: list[dict] = json.loads(SYMPTOMS_FILE.read_text(encoding="utf-8"))
    # Only items with parent_group set
    items_with_parent = [i for i in items if i.get("payload", {}).get("parent_group")]

    if not items_with_parent:
        print("No items with parent_group found in pdf_symptoms.json.")
        return 0

    from db.session import AsyncSessionLocal
    from db.models import AromaCardModel
    from sqlalchemy import select

    updated = 0
    async with AsyncSessionLocal() as session:
        for item in items_with_parent:
            slug = item["slug"]
            parent_group = item["payload"]["parent_group"]
            category_group = item["payload"].get("category_group", "")

            result = await session.execute(
                select(AromaCardModel).where(AromaCardModel.slug == slug)
            )
            card = result.scalar_one_or_none()
            if card is None:
                print(f"  SKIP (not found): {slug}")
                continue

            new_payload = {**card.payload, "parent_group": parent_group, "category_group": category_group}
            if dry_run:
                print(f"  DRY-RUN: {slug} → parent_group={parent_group!r}, category_group={category_group!r}")
            else:
                card.payload = new_payload
                updated += 1

        if not dry_run:
            await session.commit()

    label = "Would update" if dry_run else "Updated"
    total = len(items_with_parent)
    print(f"\nDone: {label} {updated if not dry_run else total}/{total} symptom cards.")
    return updated


def main() -> None:
    parser = argparse.ArgumentParser(description="Reseed symptom parent_group hierarchy")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing to DB")
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
