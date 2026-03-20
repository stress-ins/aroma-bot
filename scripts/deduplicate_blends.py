#!/usr/bin/env python3
"""One-time script: remove duplicate blend cards from aroma_cards.

Duplicates arise from two import sources creating different slugs for the same
blend (PDF import → Cyrillic slug, handbook import → transliterated slug).

Strategy:
  - Group blends by normalized name.
  - For each group with >1 slug, keep the transliterated (ASCII) slug, delete others.
  - Update any symptom cards whose recommended_blend_slugs reference deleted slugs.

Run on VPS:
  cd /opt/aroma && .venv/bin/python scripts/deduplicate_blends.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select, delete, update

from db.models import AromaCardModel
from db.session import AsyncSessionLocal


def _is_ascii_slug(slug: str) -> bool:
    """Return True if slug contains only ASCII characters."""
    return all(ord(c) < 128 for c in slug)


def _normalize_name(name: str) -> str:
    """Lowercase, strip, collapse whitespace."""
    return " ".join(name.lower().strip().replace("ё", "е").split())


# Manual overrides: for specific known duplicates where names differ slightly
_MANUAL_GROUPS: dict[str, str] = {
    # "smesh-ot-glaz" and "смесь-для-глаз" have different names but same blend
    "смесь-для-глаз": "smesh-ot-glaz",
    # Typo variants
    "smesh-ot-morschin": "smesh-ot-morshchin",
    "смесь-от-морщин": "smesh-ot-morshchin",
    # Numbered duplicates
    "smesh-ot-ukrepleniya-i-povysheniya-2": "smesh-ot-ukrepleniya-i-povysheniya",
    "smesh-ot-ukrepleniya-i-povysheniya-tonusa-myshts-2": "smesh-ot-ukrepleniya-i-povysheniya-tonusa-myshts-1",
    # Brand name typo
    "blend-juva-cleance": "blend-juvacleanse",
}


async def main() -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AromaCardModel).where(AromaCardModel.category == "blend")
        )
        blends = result.scalars().all()
        print(f"Total blend cards: {len(blends)}")

        # Group by normalized name
        name_groups: dict[str, list[AromaCardModel]] = {}
        for b in blends:
            key = _normalize_name(b.name)
            name_groups.setdefault(key, []).append(b)

        slugs_to_delete: list[str] = []
        slug_remap: dict[str, str] = {}  # deleted_slug → kept_slug

        # 1. Process name-based duplicates
        for name, group in name_groups.items():
            if len(group) < 2:
                continue
            # Prefer ASCII slug
            ascii_slugs = [b for b in group if _is_ascii_slug(b.slug)]
            if ascii_slugs:
                keeper = ascii_slugs[0]
            else:
                keeper = group[0]
            for b in group:
                if b.slug != keeper.slug:
                    slugs_to_delete.append(b.slug)
                    slug_remap[b.slug] = keeper.slug
                    print(f"  DELETE {b.slug!r} (keep {keeper.slug!r}, name={name!r})")

        # 2. Process manual overrides
        slug_index = {b.slug: b for b in blends}
        for bad_slug, good_slug in _MANUAL_GROUPS.items():
            if bad_slug in slug_index and good_slug in slug_index and bad_slug not in slugs_to_delete:
                slugs_to_delete.append(bad_slug)
                slug_remap[bad_slug] = good_slug
                print(f"  DELETE {bad_slug!r} (manual → {good_slug!r})")

        if not slugs_to_delete:
            print("No duplicates found.")
            return

        print(f"\nWill delete {len(slugs_to_delete)} duplicate blend(s).")

        # 3. Update symptom cards that reference deleted slugs
        symptom_result = await session.execute(
            select(AromaCardModel).where(AromaCardModel.category == "symptom")
        )
        symptoms = symptom_result.scalars().all()
        updated_symptoms = 0

        for s in symptoms:
            payload = dict(s.payload or {})
            blend_slugs = list(payload.get("recommended_blend_slugs") or [])
            blend_names = list(payload.get("recommended_blend_names") or [])
            changed = False

            new_slugs = []
            new_names = []
            seen = set()
            for i, slug in enumerate(blend_slugs):
                remapped = slug_remap.get(slug, slug)
                if remapped in seen:
                    changed = True
                    continue
                seen.add(remapped)
                if remapped != slug:
                    changed = True
                new_slugs.append(remapped)
                new_names.append(blend_names[i] if i < len(blend_names) else "")

            if changed:
                payload["recommended_blend_slugs"] = new_slugs
                payload["recommended_blend_names"] = new_names
                s.payload = payload
                updated_symptoms += 1

        print(f"Updated {updated_symptoms} symptom card(s) with remapped blend slugs.")

        # 4. Delete duplicate cards
        await session.execute(
            delete(AromaCardModel).where(AromaCardModel.slug.in_(slugs_to_delete))
        )

        await session.commit()
        print(f"Deleted {len(slugs_to_delete)} duplicate blend card(s). Done.")


if __name__ == "__main__":
    asyncio.run(main())
