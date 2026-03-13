"""
Import PDF-extracted handbook data into the database.

Usage:
    python scripts/import_handbook_data.py

Steps:
1. Patch existing oil cards with new fields (article_number, complementary_oils, etc.)
2. Insert new oil cards
3. Insert blend cards
4. Insert symptom cards
"""
from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Mapping
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from db.session import AsyncSessionLocal
from db.models import AromaCardModel

DATA_DIR = Path(__file__).parent.parent / "data"

OILS_PATCH_FILE = DATA_DIR / "pdf_oils_patch.json"
OILS_NEW_FILE = DATA_DIR / "pdf_oils_new.json"
BLENDS_FILE = DATA_DIR / "pdf_blends.json"
SYMPTOMS_FILE = DATA_DIR / "pdf_symptoms.json"


def _coerce_payload(value: object) -> dict[str, object]:
    if isinstance(value, str):
        value = json.loads(value)
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _coerce_aliases(value: object) -> list[str]:
    if isinstance(value, str):
        value = json.loads(value)
    if isinstance(value, list):
        return [str(item) for item in value]
    return []


def _deep_merge_patch(existing_payload: dict, patch: dict) -> dict:
    """Merge patch fields into existing payload, only setting non-empty values."""
    merged = dict(existing_payload)
    for key, value in patch.items():
        if key.startswith("__"):
            continue
        # Only update if value is non-empty and field not already set with real data
        if isinstance(value, list):
            if value:  # only if non-empty list
                merged[key] = value
        elif isinstance(value, str):
            if value.strip():  # only if non-empty string
                # For therapeutic_properties etc., don't overwrite if existing value is long
                existing = str(merged.get(key, "") or "").strip()
                if not existing or len(existing) < 20:
                    merged[key] = value.strip()
                elif key in ("article_number", "name_en", "name_ru"):
                    # Always update these
                    merged[key] = value.strip()
        elif value is not None:
            merged[key] = value
    return merged


async def patch_existing_oils(session, oils_patch: list[dict]) -> tuple[int, int]:
    """Apply new fields to existing oil cards."""
    updated = 0
    skipped = 0

    for entry in oils_patch:
        slug = entry["slug"]
        patch = entry.get("patch", {})
        if not patch:
            skipped += 1
            continue

        stmt = select(AromaCardModel).where(AromaCardModel.slug == slug)
        result = await session.execute(stmt)
        model = result.scalar_one_or_none()

        if not model:
            print(f"  WARNING: slug '{slug}' not found in DB, skipping patch")
            skipped += 1
            continue

        existing_payload = _coerce_payload(model.payload)
        merged_payload = _deep_merge_patch(existing_payload, patch)

        if merged_payload != existing_payload:
            model.payload = merged_payload
            updated += 1

    return updated, skipped


async def upsert_cards(session, cards: list[dict], label: str) -> tuple[int, int]:
    """Insert or update cards."""
    inserted = 0
    updated = 0

    for card in cards:
        slug = card["slug"]
        name = card.get("name", slug)
        category = card.get("category", "aroma")
        source_type = card.get("source_type", "herb")
        aliases = _coerce_aliases(card.get("aliases", []))
        payload = _coerce_payload(card.get("payload", {}))

        stmt = select(AromaCardModel).where(AromaCardModel.slug == slug)
        result = await session.execute(stmt)
        model = result.scalar_one_or_none()

        if model:
            # Update existing
            model.name = name
            model.category = category
            model.source_type = source_type
            model.aliases = aliases
            existing_payload = _coerce_payload(model.payload)
            merged = _deep_merge_patch(existing_payload, payload)
            model.payload = merged
            updated += 1
        else:
            # Insert new
            new_card = AromaCardModel(
                slug=slug,
                name=name,
                category=category,
                source_type=source_type,
                aliases=aliases,
                payload=payload,
            )
            session.add(new_card)
            inserted += 1

    return inserted, updated


async def main() -> None:
    # Verify files exist
    missing = [f for f in [OILS_PATCH_FILE, OILS_NEW_FILE, BLENDS_FILE, SYMPTOMS_FILE] if not f.exists()]
    if missing:
        print(f"ERROR: Missing files: {[str(f) for f in missing]}")
        print("Run scripts/parse_handbook_pdf.py first")
        sys.exit(1)

    oils_patch = json.loads(OILS_PATCH_FILE.read_text(encoding="utf-8"))
    oils_new = json.loads(OILS_NEW_FILE.read_text(encoding="utf-8"))
    blends = json.loads(BLENDS_FILE.read_text(encoding="utf-8"))
    symptoms = json.loads(SYMPTOMS_FILE.read_text(encoding="utf-8"))

    print(f"Loaded:")
    print(f"  {len(oils_patch)} oil patches")
    print(f"  {len(oils_new)} new oils")
    print(f"  {len(blends)} blends")
    print(f"  {len(symptoms)} symptoms")

    async with AsyncSessionLocal() as session:
        # 1. Patch existing oils
        print("\n1. Patching existing oil cards...")
        u, s = await patch_existing_oils(session, oils_patch)
        print(f"   Updated: {u}, Skipped: {s}")

        # 2. Insert new oils
        print("2. Importing new oil cards...")
        i, u = await upsert_cards(session, oils_new, "oil")
        print(f"   Inserted: {i}, Updated: {u}")

        # 3. Import blends
        print("3. Importing blend cards...")
        i, u = await upsert_cards(session, blends, "blend")
        print(f"   Inserted: {i}, Updated: {u}")

        # 4. Import symptoms
        print("4. Importing symptom cards...")
        i, u = await upsert_cards(session, symptoms, "symptom")
        print(f"   Inserted: {i}, Updated: {u}")

        await session.commit()

    print("\nDone! DB summary:")
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AromaCardModel.category, AromaCardModel.slug).order_by(AromaCardModel.category)
        )
        rows = result.all()
        from collections import Counter
        counts = Counter(row[0] for row in rows)
        for cat, count in sorted(counts.items()):
            print(f"  {cat}: {count}")
        print(f"  TOTAL: {len(rows)}")


if __name__ == "__main__":
    asyncio.run(main())
