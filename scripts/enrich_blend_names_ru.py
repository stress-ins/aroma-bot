"""Enrich blend cards: fill ingredient_names_ru from aroma cards via slug lookup.

For each blend card where ingredient_names_ru is empty but ingredient_slugs is set,
looks up name_ru from the corresponding aroma card and stores it.

Usage:
    .venv/bin/python scripts/enrich_blend_names_ru.py [--dry-run] [--slug SLUG]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


async def run(dry_run: bool = False, slug: str | None = None) -> None:
    from db.session import AsyncSessionLocal
    from db.models import AromaCardModel
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        # Load all aroma cards to build slug→name_ru map
        aroma_result = await session.execute(
            select(AromaCardModel).where(AromaCardModel.category == "aroma")
        )
        aroma_models = aroma_result.scalars().all()
        slug_to_name_ru: dict[str, str] = {}
        for m in aroma_models:
            payload = m.payload or {}
            # name_ru preferred; fall back to model.name (seed data stores RU name in name field)
            name_ru = str(payload.get("name_ru") or m.name or "").strip()
            if m.slug and name_ru:
                slug_to_name_ru[m.slug] = name_ru

        print(f"Loaded {len(slug_to_name_ru)} aroma slugs with name_ru.")

        # Load blend cards
        blend_result = await session.execute(
            select(AromaCardModel).where(AromaCardModel.category == "blend")
        )
        blend_models = blend_result.scalars().all()

    print(f"Loaded {len(blend_models)} blend cards.")

    if slug:
        blend_models = [m for m in blend_models if m.slug == slug]
        if not blend_models:
            print(f"ERROR: no blend card found with slug={slug!r}")
            return

    updated = 0
    skipped_no_slugs = 0
    skipped_already_filled = 0

    for m in blend_models:
        payload = m.payload or {}
        ingredient_slugs: list[str] = list(payload.get("ingredient_slugs") or [])
        ingredient_names_ru: list[str] = list(payload.get("ingredient_names_ru") or [])

        if not ingredient_slugs:
            skipped_no_slugs += 1
            continue

        # Check if already fully filled (all non-empty)
        if ingredient_names_ru and all(n.strip() for n in ingredient_names_ru):
            skipped_already_filled += 1
            continue

        # Build new names_ru list from slug lookup
        new_names_ru = []
        for i, s in enumerate(ingredient_slugs):
            # Prefer existing value if present
            existing = ingredient_names_ru[i].strip() if i < len(ingredient_names_ru) else ""
            resolved = existing or slug_to_name_ru.get(s, "")
            new_names_ru.append(resolved)

        # Skip if nothing changed
        if new_names_ru == ingredient_names_ru:
            skipped_already_filled += 1
            continue

        print(f"  {m.slug}: {ingredient_names_ru!r} → {new_names_ru!r}")

        if not dry_run:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(AromaCardModel).where(AromaCardModel.id == m.id)
                )
                card = result.scalar_one()
                new_payload = dict(card.payload or {})
                new_payload["ingredient_names_ru"] = new_names_ru
                card.payload = new_payload
                await session.commit()

        updated += 1

    print(f"\nDone. Updated: {updated}, skipped (no slugs): {skipped_no_slugs}, "
          f"skipped (already filled): {skipped_already_filled}")
    if dry_run:
        print("(dry-run: no changes written)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich blend ingredient_names_ru from aroma slugs")
    parser.add_argument("--dry-run", action="store_true", help="Print changes without writing")
    parser.add_argument("--slug", default=None, help="Process only a specific blend slug")
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run, slug=args.slug))


if __name__ == "__main__":
    main()
