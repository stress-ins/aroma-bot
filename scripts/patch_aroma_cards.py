"""
Patch aroma_cards table on any environment.

Usage:
    python scripts/patch_aroma_cards.py

Applies updated payload/key/questions to all 67 aroma cards
without touching drafts or any other data.
"""
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


async def main() -> None:
    if not CARDS_JSON.exists():
        print(f"ERROR: data file not found: {CARDS_JSON}")
        sys.exit(1)

    cards = json.loads(CARDS_JSON.read_text(encoding="utf-8"))
    print(f"Loaded {len(cards)} cards from {CARDS_JSON.name}")

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
                model.payload = payload
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
    asyncio.run(main())
