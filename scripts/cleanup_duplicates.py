#!/usr/bin/env python3
"""Phase 1: Remove junk records, duplicates, and fix category mismatches.

Usage:
    .venv/bin/python scripts/cleanup_duplicates.py --dry-run   # preview
    .venv/bin/python scripts/cleanup_duplicates.py              # run
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


async def run(dry_run: bool = False) -> None:
    from sqlalchemy import select, delete, update
    from db.session import AsyncSessionLocal
    from db.models import AromaCardModel

    async with AsyncSessionLocal() as session:
        # ── 1. Delete junk records ──────────────────────────────────────
        junk_slugs = ["blend-jmhhhl", "blend-no-ru"]
        for slug in junk_slugs:
            result = await session.execute(
                select(AromaCardModel).where(AromaCardModel.slug == slug)
            )
            card = result.scalar_one_or_none()
            if card:
                print(f"  DELETE junk: {card.slug} ({card.category}, name={card.name})")
                if not dry_run:
                    await session.delete(card)

        # ── 2. Delete duplicate cards (keep the richer one) ─────────────
        dupes_to_delete = [
            # (slug_to_delete, reason)
            ("aroma-lavender", "duplicate of lavender"),
            ("aroma-rose", "duplicate of rose"),
            ("symptom-anemia", "duplicate of symptom-анемия"),
        ]
        for slug, reason in dupes_to_delete:
            result = await session.execute(
                select(AromaCardModel).where(AromaCardModel.slug == slug)
            )
            card = result.scalar_one_or_none()
            if card:
                print(f"  DELETE dupe: {card.slug} ({reason})")
                if not dry_run:
                    await session.delete(card)

        # ── 3. Merge tangerine → mandarin (keep mandarin) ──────────────
        result = await session.execute(
            select(AromaCardModel).where(AromaCardModel.slug == "tangerine")
        )
        tangerine = result.scalar_one_or_none()
        result = await session.execute(
            select(AromaCardModel).where(AromaCardModel.slug == "mandarin")
        )
        mandarin = result.scalar_one_or_none()
        if tangerine and mandarin:
            # Merge missing fields from tangerine into mandarin
            src = dict(tangerine.payload or {})
            dst = dict(mandarin.payload or {})
            merged = 0
            for key, val in src.items():
                if key.startswith("__"):
                    continue
                if val and not dst.get(key):
                    dst[key] = val
                    merged += 1
            print(f"  MERGE tangerine → mandarin ({merged} fields), then DELETE tangerine")
            if not dry_run:
                mandarin.payload = dst
                mandarin.updated_at = datetime.now(timezone.utc)
                await session.delete(tangerine)

        # ── 4. Merge nobilis → bay-laurel (keep bay-laurel) ────────────
        result = await session.execute(
            select(AromaCardModel).where(AromaCardModel.slug == "nobilis")
        )
        nobilis = result.scalar_one_or_none()
        result = await session.execute(
            select(AromaCardModel).where(AromaCardModel.slug == "bay-laurel")
        )
        bay_laurel = result.scalar_one_or_none()
        if nobilis and bay_laurel:
            src = dict(nobilis.payload or {})
            dst = dict(bay_laurel.payload or {})
            merged = 0
            for key, val in src.items():
                if key.startswith("__"):
                    continue
                if val and not dst.get(key):
                    dst[key] = val
                    merged += 1
            print(f"  MERGE nobilis → bay-laurel ({merged} fields), then DELETE nobilis")
            if not dry_run:
                bay_laurel.payload = dst
                bay_laurel.updated_at = datetime.now(timezone.utc)
                await session.delete(nobilis)

        # ── 5. Re-categorize symptom-recipes as blends ──────────────────
        recipe_symptom_slugs = [
            "symptom-смесь-от-волчанки",
            "symptom-смесь-от-пневмонии",
            "symptom-отхаркивающая-смесь",
            "symptom-смесь-от-морщин",
            "symptom-смесь-от-перхоти",
            "symptom-смесь-для-глаз",
        ]
        for slug in recipe_symptom_slugs:
            result = await session.execute(
                select(AromaCardModel).where(AromaCardModel.slug == slug)
            )
            card = result.scalar_one_or_none()
            if card:
                new_slug = slug.replace("symptom-", "")
                # Check if blend already exists on VPS
                result2 = await session.execute(
                    select(AromaCardModel).where(AromaCardModel.slug == new_slug)
                )
                existing = result2.scalar_one_or_none()
                if existing:
                    print(f"  DELETE symptom-recipe: {slug} (blend {new_slug} already exists)")
                    if not dry_run:
                        await session.delete(card)
                else:
                    print(f"  RECATEGORIZE: {slug} → blend/{new_slug}")
                    if not dry_run:
                        card.category = "blend"
                        card.slug = new_slug
                        card.updated_at = datetime.now(timezone.utc)

        # ── 6. Fix blend-thieves description artifact ───────────────────
        result = await session.execute(
            select(AromaCardModel).where(AromaCardModel.slug == "blend-thieves")
        )
        thieves = result.scalar_one_or_none()
        if thieves:
            payload = dict(thieves.payload or {})
            desc = str(payload.get("description", "")).strip()
            if desc and len(desc) < 10:
                print(f"  FIX blend-thieves: description '{desc}' → cleared for re-enrichment")
                if not dry_run:
                    payload["description"] = ""
                    payload.pop("description_short", None)
                    thieves.payload = payload
                    thieves.updated_at = datetime.now(timezone.utc)

        if not dry_run:
            await session.commit()
            print("\nCommitted to database.")
        else:
            print("\n[DRY RUN] No changes made.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run))
