"""Patch oil reflection questions into aroma_cards.

Idempotent: only updates cards where questions field is empty or missing.
Run: .venv/bin/python scripts/patch_oil_questions.py [--force]
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

PATCH_FILE = Path(__file__).parent.parent / "data" / "oil_questions_patch.json"


async def main():
    force = "--force" in sys.argv

    from db.session import AsyncSessionLocal
    from sqlalchemy import select, update
    from db.models import AromaCardModel

    patch = json.loads(PATCH_FILE.read_text(encoding="utf-8"))
    questions_map: dict[str, str] = patch["questions"]

    print(f"Loaded {len(questions_map)} oil questions from {PATCH_FILE.name}")

    updated = 0
    skipped = 0

    async with AsyncSessionLocal() as session:
        for slug, questions_text in questions_map.items():
            result = await session.execute(
                select(AromaCardModel).where(AromaCardModel.slug == slug)
            )
            card = result.scalar_one_or_none()
            if not card:
                print(f"  SKIP {slug}: card not found")
                skipped += 1
                continue

            existing = (card.payload or {}).get("questions", "")
            if existing and not force:
                print(f"  SKIP {slug}: already has questions ({len(existing)} chars)")
                skipped += 1
                continue

            payload = dict(card.payload or {})
            payload["questions"] = questions_text
            card.payload = payload
            updated += 1
            print(f"  SET  {slug}: {len(questions_text)} chars")

        await session.commit()

    print(f"\nDone: {updated} updated, {skipped} skipped")


if __name__ == "__main__":
    asyncio.run(main())
