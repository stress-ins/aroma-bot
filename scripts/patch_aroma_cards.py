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

from db.session import AsyncSessionLocal
from sqlalchemy import text

# Exported card data (payload already contains all edits)
CARDS_JSON = Path(__file__).parent.parent / "scripts" / "aroma_cards_data.json"


async def main() -> None:
    if not CARDS_JSON.exists():
        print(f"ERROR: data file not found: {CARDS_JSON}")
        sys.exit(1)

    cards = json.loads(CARDS_JSON.read_text(encoding="utf-8"))
    print(f"Loaded {len(cards)} cards from {CARDS_JSON.name}")

    async with AsyncSessionLocal() as s:
        updated = 0
        skipped = 0
        for card in cards:
            # Check if row exists
            row = await s.execute(
                text("SELECT id FROM aroma_cards WHERE slug = :slug"),
                {"slug": card["slug"]},
            )
            existing = row.fetchone()

            if existing:
                await s.execute(
                    text(
                        "UPDATE aroma_cards SET "
                        "name=:name, source_type=:source_type, aliases=:aliases, "
                        "payload=:payload, category=:category, "
                        "updated_at=CURRENT_TIMESTAMP "
                        "WHERE slug=:slug"
                    ),
                    {
                        "name": card["name"],
                        "source_type": card["source_type"],
                        "aliases": card["aliases"],
                        "payload": card["payload"],
                        "category": card["category"],
                        "slug": card["slug"],
                    },
                )
                updated += 1
            else:
                await s.execute(
                    text(
                        "INSERT INTO aroma_cards (slug, name, source_type, aliases, payload, category) "
                        "VALUES (:slug, :name, :source_type, :aliases, :payload, :category)"
                    ),
                    {
                        "slug": card["slug"],
                        "name": card["name"],
                        "source_type": card["source_type"],
                        "aliases": card["aliases"],
                        "payload": card["payload"],
                        "category": card["category"],
                    },
                )
                updated += 1
                skipped += 1  # actually inserted

        await s.commit()

    print(f"Done: {updated} cards upserted ({updated - skipped} updated, {skipped} inserted)")


if __name__ == "__main__":
    asyncio.run(main())
