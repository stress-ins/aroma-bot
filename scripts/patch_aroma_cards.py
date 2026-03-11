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
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from db.session import AsyncSessionLocal
from db.models import AromaCardModel

# Exported card data (payload already contains all edits)
CARDS_JSON = Path(__file__).parent.parent / "scripts" / "aroma_cards_data.json"


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
            
            # Check if row exists using model
            stmt = select(AromaCardModel).filter(AromaCardModel.slug == slug)
            result = await session.execute(stmt)
            model = result.scalar_one_or_none()

            # Ensure aliases is a list
            aliases = card_data.get("aliases", [])
            if isinstance(aliases, str):
                try:
                    aliases = json.loads(aliases)
                except:
                    aliases = []

            # Ensure payload is a dict
            payload = card_data.get("payload", {})
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except:
                    payload = {}

            if model:
                model.name = card_data["name"]
                model.source_type = card_data["source_type"]
                model.aliases = aliases
                model.payload = payload
                model.category = card_data.get("category", "aroma")
                updated += 1
            else:
                new_card = AromaCardModel(
                    slug=slug,
                    name=card_data["name"],
                    source_type=card_data["source_type"],
                    aliases=aliases,
                    payload=payload,
                    category=card_data.get("category", "aroma"),
                )
                session.add(new_card)
                inserted += 1

        await session.commit()

    print(f"Done: {updated + inserted} cards processed ({updated} updated, {inserted} inserted)")


if __name__ == "__main__":
    asyncio.run(main())
