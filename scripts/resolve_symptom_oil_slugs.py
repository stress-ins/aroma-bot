"""Resolve unmatched English oil names in symptom recommended_oil_slugs.

Tries to match each unresolved oil name against:
1. AromaCardModel.slug exact match
2. AromaCardModel.aliases (case-insensitive)
3. payload["name"] / payload["name_ru"] (case-insensitive)

Outputs:
- Updates symptom payloads with newly resolved slugs (unless --dry-run)
- Writes scripts/missing_oils.txt with names that could not be resolved

Usage:
    .venv/bin/python scripts/resolve_symptom_oil_slugs.py [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

MISSING_FILE = Path(__file__).parent / "missing_oils.txt"


async def run(dry_run: bool = False) -> None:
    from db.session import AsyncSessionLocal
    from db.models import AromaCardModel
    from sqlalchemy import select
    from datetime import datetime, timezone

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(AromaCardModel))
        all_models = result.scalars().all()

    # Build name → slug lookup from all aroma cards
    lookup: dict[str, str] = {}
    for card in all_models:
        if card.category != "aroma":
            continue
        slug = card.slug
        lookup[slug.lower()] = slug
        for alias in (card.aliases or []):
            if alias:
                lookup[alias.strip().lower()] = slug
        p = card.payload or {}
        for field in ("name", "name_ru"):
            val = (p.get(field) or "").strip().lower()
            if val:
                lookup[val] = slug

    symptom_cards = [m for m in all_models if m.category == "symptom"]

    resolved_count = 0
    missing: set[str] = set()
    updates: list[tuple[AromaCardModel, dict]] = []

    for sym in symptom_cards:
        p = dict(sym.payload or {})
        names: list[str] = list(p.get("recommended_oil_names") or [])
        slugs: list[str] = list(p.get("recommended_oil_slugs") or [])

        # Pad slugs to match names length
        while len(slugs) < len(names):
            slugs.append("")

        changed = False
        for i, name in enumerate(names):
            if slugs[i]:
                continue  # already resolved
            if not name:
                continue
            resolved = lookup.get(name.strip().lower())
            if resolved:
                slugs[i] = resolved
                changed = True
                resolved_count += 1
            else:
                missing.add(name.strip())

        if changed:
            p["recommended_oil_slugs"] = slugs
            updates.append((sym, p))

    print(f"Resolved: {resolved_count} oil slugs across {len(updates)} symptom cards")
    print(f"Missing (unresolved): {len(missing)}")

    if missing:
        MISSING_FILE.write_text("\n".join(sorted(missing)), encoding="utf-8")
        print(f"Written: {MISSING_FILE}")

    if dry_run:
        print("Dry run — no changes written.")
        if missing:
            print("\nUnresolved oil names:")
            for name in sorted(missing):
                print(f"  {name}")
        return

    if not updates:
        print("Nothing to update.")
        return

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(AromaCardModel))
        db_map = {m.slug: m for m in result.scalars().all()}
        for sym, new_payload in updates:
            m = db_map.get(sym.slug)
            if not m:
                continue
            m.payload = new_payload
            m.updated_at = datetime.now(timezone.utc)
        await session.commit()

    print(f"Done: {len(updates)} symptom cards updated.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Print changes without writing to DB")
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
