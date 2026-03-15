#!/usr/bin/env python3
"""Phase 2: Clean up garbage entries in blend ingredient_names.

Removes entries > 60 chars, entries with sentence-like patterns,
page numbers, and other PDF extraction artifacts.

Usage:
    .venv/bin/python scripts/cleanup_blend_ingredients.py --dry-run
    .venv/bin/python scripts/cleanup_blend_ingredients.py
"""
from __future__ import annotations

import argparse
import asyncio
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def is_garbage(entry: str) -> bool:
    """Return True if an ingredient_names entry looks like garbage."""
    s = entry.strip()
    if not s:
        return True
    if len(s) > 60:
        return True
    # Contains sentence-ending punctuation mid-string (not just trailing period)
    if re.search(r"\.\s+[A-ZА-Я]", s):
        return True
    # Starts with lowercase (likely continuation of a sentence)
    if s[0].islower() and not s[0].isdigit():
        return True
    # Looks like a page number
    if re.match(r"^\d{1,3}$", s):
        return True
    # Contains multiple sentences (more than one period)
    if s.count(".") > 1:
        return True
    # Very long words typical of run-together PDF text
    if any(len(word) > 30 for word in s.split()):
        return True
    # Contains common sentence markers
    sentence_markers = ["можно", "нанос", "распыл", "использ", "добав", "помож", "способ",
                        "создан", "снижа", "подход", "возник", "област", "бодряш"]
    lower = s.lower()
    if any(marker in lower for marker in sentence_markers):
        # But allow if it looks like a short name with parentheses
        if "(" in s and ")" in s and len(s) < 40:
            return False
        return True
    return False


async def run(dry_run: bool = False) -> None:
    from sqlalchemy import select
    from db.session import AsyncSessionLocal
    from db.models import AromaCardModel

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AromaCardModel).where(AromaCardModel.category == "blend")
        )
        blends = result.scalars().all()

        total_cleaned = 0
        total_removed = 0

        for blend in blends:
            payload = dict(blend.payload or {})
            names = list(payload.get("ingredient_names") or [])
            if not names:
                continue

            clean = [n for n in names if not is_garbage(n)]
            removed = len(names) - len(clean)

            if removed > 0:
                print(f"  {blend.slug}: {len(names)} → {len(clean)} ({removed} removed)")
                for n in names:
                    if is_garbage(n):
                        print(f"    ✗ {n[:80]}")
                total_cleaned += 1
                total_removed += removed

                if not dry_run:
                    payload["ingredient_names"] = clean
                    blend.payload = payload
                    blend.updated_at = datetime.now(timezone.utc)

        if not dry_run:
            await session.commit()

        print(f"\nDone: {total_cleaned} blends cleaned, {total_removed} garbage entries removed")
        if dry_run:
            print("[DRY RUN] No changes made.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run))
