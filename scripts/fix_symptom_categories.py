"""Fix misclassified symptom category_groups and add missing БЕРЕМЕННОСТЬ card.

This is a one-shot migration script:
  1. Updates category_group for 8 cards that were erroneously set to "РАК ШЕЙКИ МАТКИ"
     due to PDF parsing errors in an earlier import.
  2. Inserts БЕРЕМЕННОСТЬ as a standalone symptom card if it doesn't exist.
  3. After running, execute classify_symptom_hierarchy.py to update parent_groups.

Usage:
    .venv/bin/python scripts/fix_symptom_categories.py [--dry-run]
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

# Cards whose category_group was wrongly set to "РАК ШЕЙКИ МАТКИ" by PDF parser
CATEGORY_FIXES = {
    "symptom-опухоли":                     "РАК",
    "symptom-сибирская-язва":              "АНТИСЕПТИКИ И ДЕЗИНФИЦИРУЮЩИЕ СРЕДСТВА",
    "symptom-цинга":                       "ИММУННАЯ СИСТЕМА",
    "symptom-альцгеимера-болезнь":          "БОЛЕЗНИ НЕРВНОЙ СИСТЕМЫ",
    "symptom-конвульсии-судороги":         "БОЛЕЗНИ НЕРВНОЙ СИСТЕМЫ",
    "symptom-концентрация-нарушенная":     "РАССЕЯННОСТЬ",
    "symptom-обморок":                     "ВЕГЕТАТИВНАЯ НЕРВНАЯ СИСТЕМА",
    "symptom-память-нарушенная":           "РАССЕЯННОСТЬ",
}


async def run(dry_run: bool = False) -> None:
    from db.session import AsyncSessionLocal
    from db.models import AromaCardModel
    from sqlalchemy import select

    # Load seed data to get the БЕРЕМЕННОСТЬ card definition
    items: list[dict] = json.loads(SYMPTOMS_FILE.read_text(encoding="utf-8"))
    pregnancy_seed = next((i for i in items if i["slug"] == "symptom-беременность"), None)

    fixed = 0
    inserted = 0

    async with AsyncSessionLocal() as session:
        # 1. Fix category_group for misclassified cards
        for slug, correct_group in CATEGORY_FIXES.items():
            result = await session.execute(select(AromaCardModel).where(AromaCardModel.slug == slug))
            card = result.scalar_one_or_none()
            if card is None:
                print(f"  SKIP (not found): {slug}")
                continue
            old_group = (card.payload or {}).get("category_group", "")
            if old_group == correct_group:
                print(f"  OK (already correct): {slug}")
                continue
            if dry_run:
                print(f"  DRY-RUN fix: {slug}  {old_group!r} → {correct_group!r}")
            else:
                new_payload = {**card.payload, "category_group": correct_group}
                card.payload = new_payload
                print(f"  Fixed: {slug}  {old_group!r} → {correct_group!r}")
            fixed += 1

        # 2. Insert БЕРЕМЕННОСТЬ card
        if pregnancy_seed:
            result = await session.execute(
                select(AromaCardModel).where(AromaCardModel.slug == "symptom-беременность")
            )
            existing = result.scalar_one_or_none()
            if existing:
                print(f"  OK (already exists): symptom-беременность")
            else:
                if dry_run:
                    print(f"  DRY-RUN insert: symptom-беременность (БЕРЕМЕННОСТЬ)")
                else:
                    new_card = AromaCardModel(
                        slug=pregnancy_seed["slug"],
                        name=pregnancy_seed["name"],
                        category=pregnancy_seed["category"],
                        source_type=pregnancy_seed["source_type"],
                        aliases=pregnancy_seed.get("aliases", []),
                        payload=pregnancy_seed["payload"],
                    )
                    session.add(new_card)
                    print(f"  Inserted: symptom-беременность (БЕРЕМЕННОСТЬ)")
                inserted += 1
        else:
            print("  WARN: symptom-беременность not found in pdf_symptoms.json")

        if not dry_run:
            await session.commit()

    label = "Would update" if dry_run else "Done"
    print(f"\n{label}: {fixed} category_group fixes, {inserted} new cards inserted.")
    if not dry_run and (fixed > 0 or inserted > 0):
        print("\nNext step: run classify_symptom_hierarchy.py to update parent_groups.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fix misclassified symptom categories")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing to DB")
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
