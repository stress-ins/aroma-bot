#!/usr/bin/env python3
"""Import blends from data/base_blends.json into the blends SQLite table.

Uses parse_base_blends.py to produce the JSON if it doesn't exist,
then upserts each blend into the dedicated blends table.

Usage:
    .venv/bin/python scripts/import_blend_pdfs.py --dry-run   # preview
    .venv/bin/python scripts/import_blend_pdfs.py              # import
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

JSON_PATH = ROOT / "data" / "base_blends.json"


def _map_ingredients(payload: dict) -> list[dict]:
    """Map parse_base_blends payload to BlendModel ingredients format."""
    slugs = payload.get("ingredient_slugs") or []
    names = payload.get("ingredient_names_ru") or payload.get("ingredient_names") or []
    drops = payload.get("ingredient_drops") or []

    ingredients = []
    for i, slug in enumerate(slugs):
        ingredients.append({
            "oil_slug": slug,
            "oil_name": names[i] if i < len(names) else slug,
            "ratio": float(drops[i]) if i < len(drops) and drops[i] else 0.0,
            "unit": "капли",
        })
    return ingredients


async def import_blends(dry_run: bool = False) -> int:
    from db.session import init_db
    from bot.services.blends_store import upsert_blend

    await init_db()

    if not JSON_PATH.exists():
        print(f"JSON not found: {JSON_PATH}")
        print("Run: .venv/bin/python scripts/parse_base_blends.py")
        return 0

    with open(JSON_PATH, encoding="utf-8") as f:
        cards = json.load(f)

    count = 0
    for card in cards:
        payload = card.get("payload", {})
        slug = card.get("slug", "")
        name = payload.get("name_ru") or card.get("name", "")
        goal = payload.get("description", "")[:500]
        ingredients = _map_ingredients(payload)

        if dry_run:
            print(f"  [{slug}] {name} — {len(ingredients)} ingredients")
        else:
            await upsert_blend(
                slug=slug,
                name=name,
                goal=goal,
                ingredients=ingredients,
                indications=goal,
                source_pdf=payload.get("source_pdf", ""),
            )
        count += 1

    print(f"{'[DRY RUN] ' if dry_run else ''}Processed {count} blends")
    return count


def main():
    parser = argparse.ArgumentParser(description="Import blends into SQLite")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(import_blends(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
