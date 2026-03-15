"""
Patch aroma_cards table on any environment.

Usage:
    python scripts/patch_aroma_cards.py
    python scripts/patch_aroma_cards.py --slug lavender
    python scripts/patch_aroma_cards.py --force-overwrite --slug lavender
    python scripts/patch_aroma_cards.py --force-overwrite --confirm

Applies updated payload/key/questions to aroma cards using merge-strategy by default
(AI-enriched fields like description_short, name_ru, etc. are preserved).

--force-overwrite: replace payload entirely from JSON, discarding any enriched fields.
  Requires either --slug (single card) or --confirm (all cards) to prevent accidents.
"""
import argparse
import asyncio
import json
import sys
from collections.abc import Mapping
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from db.session import AsyncSessionLocal
from db.models import AromaCardModel

# Seed/import payload for patching aroma_cards rows in the database.
# This file is not a runtime source of truth for the miniapp.
CARDS_JSON = Path(__file__).parent.parent / "scripts" / "aroma_cards_data.json"


def _coerce_aliases(value: object) -> list[str]:
    if isinstance(value, str):
        value = json.loads(value)
    if isinstance(value, list):
        return [str(item) for item in value]
    return []


def _coerce_payload(value: object) -> dict[str, object]:
    if isinstance(value, str):
        value = json.loads(value)
    if isinstance(value, Mapping):
        return dict(value)
    return {}


async def main(slug_filter: str | None = None, force_overwrite: bool = False) -> None:
    if not CARDS_JSON.exists():
        print(f"ERROR: data file not found: {CARDS_JSON}")
        sys.exit(1)

    cards = json.loads(CARDS_JSON.read_text(encoding="utf-8"))
    if slug_filter:
        cards = [c for c in cards if c["slug"] == slug_filter]
        if not cards:
            print(f"ERROR: no card with slug '{slug_filter}' found in JSON")
            sys.exit(1)
    print(f"Loaded {len(cards)} cards from {CARDS_JSON.name}")
    if force_overwrite:
        print("WARNING: --force-overwrite mode — AI-enriched fields will be discarded")

    async with AsyncSessionLocal() as session:
        updated = 0
        inserted = 0

        for card_data in cards:
            slug = card_data["slug"]
            aliases = _coerce_aliases(card_data.get("aliases", []))
            payload = _coerce_payload(card_data.get("payload", {}))
            category = card_data.get("category", "aroma")
            name = card_data.get("name", slug)
            source_type = card_data.get("source_type", "herb")

            # Check if row exists using model
            stmt = select(AromaCardModel).filter(AromaCardModel.slug == slug)
            result = await session.execute(stmt)
            model = result.scalar_one_or_none()

            if model:
                model.name = name
                model.source_type = source_type
                model.aliases = aliases
                if force_overwrite:
                    # Replace payload entirely — use only when accumulated enrichment is stale
                    model.payload = payload
                else:
                    # Merge: JSON updates base fields; AI-enriched fields (not in JSON) are preserved.
                    # Fields like description_short, name_ru, health_effects, conditions_for_use,
                    # complementary_oil_slugs etc. are written by enrichment scripts — not in the JSON.
                    existing = dict(model.payload or {})
                    existing.update(payload)
                    model.payload = existing
                model.category = category
                updated += 1
            else:
                new_card = AromaCardModel(
                    slug=slug,
                    name=name,
                    source_type=source_type,
                    aliases=aliases,
                    payload=payload,
                    category=category,
                )
                session.add(new_card)
                inserted += 1

        await session.commit()

    print(f"Done: {updated + inserted} cards processed ({updated} updated, {inserted} inserted)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Patch aroma_cards table from JSON")
    parser.add_argument("--slug", help="Only patch this specific slug")
    parser.add_argument(
        "--force-overwrite",
        action="store_true",
        help="Replace payload entirely (discards AI-enriched fields). Requires --slug or --confirm.",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Required when using --force-overwrite on all cards (safety guard).",
    )
    args = parser.parse_args()

    if args.force_overwrite and not args.slug and not args.confirm:
        print("ERROR: --force-overwrite on all cards requires --confirm to prevent accidents")
        print("  Single card: python scripts/patch_aroma_cards.py --force-overwrite --slug lavender")
        print("  All cards:   python scripts/patch_aroma_cards.py --force-overwrite --confirm")
        sys.exit(1)

    asyncio.run(main(slug_filter=args.slug, force_overwrite=args.force_overwrite))
