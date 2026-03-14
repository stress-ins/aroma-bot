#!/usr/bin/env python3
"""One-time script: fix empty ingredient_slugs for 'Black spruce / Черная ель' in blend cards."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select  # noqa: E402

from db.models import AromaCardModel  # noqa: E402
from db.session import AsyncSessionLocal  # noqa: E402

_BLACK_SPRUCE_SLUG = "black-spruce"
_MATCH_NAMES = {"black spruce", "черная ель", "black-spruce"}


def _needs_fix(names: list, slugs: list) -> list[int]:
    """Return indices where name matches black spruce but slug is empty/missing."""
    indices = []
    for i, name in enumerate(names):
        name_lower = (name or "").lower()
        if any(n in name_lower for n in _MATCH_NAMES):
            slug = slugs[i] if i < len(slugs) else ""
            if not slug:
                indices.append(i)
    return indices


async def main() -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AromaCardModel).where(AromaCardModel.category == "blend")
        )
        cards = result.scalars().all()

        updated = 0
        for card in cards:
            payload = dict(card.payload or {})
            names = list(payload.get("ingredient_names", []) or [])
            slugs = list(payload.get("ingredient_slugs", []) or [])

            while len(slugs) < len(names):
                slugs.append("")

            indices = _needs_fix(names, slugs)
            if not indices:
                continue

            for idx in indices:
                slugs[idx] = _BLACK_SPRUCE_SLUG
                print(f"  blend {card.slug}: ingredient[{idx}] '{names[idx]}' → slug '{_BLACK_SPRUCE_SLUG}'")

            payload["ingredient_slugs"] = slugs
            card.payload = payload
            session.add(card)
            updated += 1

        await session.commit()
        print(f"Done. Updated {updated} blend card(s).")


if __name__ == "__main__":
    asyncio.run(main())
