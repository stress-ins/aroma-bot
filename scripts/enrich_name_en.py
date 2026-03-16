"""One-time script: fill missing name_en for aroma cards."""

import asyncio
import logging

from sqlalchemy import select

from db.models import AromaCardModel
from db.session import AsyncSessionLocal

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

# slug → English name mapping for cards that lack name_en
SLUG_TO_EN: dict[str, str] = {
    "balsam-fir": "Balsam Fir",
    "basil": "Basil",
    "bergamot": "Bergamot",
    "black-pepper": "Black Pepper",
    "black-spruce": "Black Spruce",
    "blue-spruce": "Blue Spruce",
    "blue-tansy": "Blue Tansy",
    "cassia": "Cassia",
    "cedarwood": "Cedarwood",
    "cinnamon": "Cinnamon",
    "citronella": "Citronella",
    "clary-sage": "Clary Sage",
    "clove": "Clove",
    "copaiba": "Copaiba",
    "cypress": "Cypress",
    "eucalyptus-globulus": "Eucalyptus Globulus",
    "fennel": "Fennel",
    "fragonia": "Fragonia",
    "frankincense": "Frankincense",
    "geranium": "Geranium",
    "german-chamomile": "German Chamomile",
    "ginger": "Ginger",
    "grapefruit": "Grapefruit",
    "helichrysum": "Helichrysum",
    "ho-wood": "Ho Wood",
    "jasmine": "Jasmine",
    "juniper": "Juniper",
    "kunzea": "Kunzea",
    "lavender": "Lavender",
    "ledum": "Ledum",
    "lemon": "Lemon",
    "lemongrass": "Lemongrass",
    "lime": "Lime",
    "marjoram": "Marjoram",
    "myrrh": "Myrrh",
    "neroli": "Neroli",
    "orange": "Orange",
    "oregano": "Oregano",
    "patchouli": "Patchouli",
    "peppermint": "Peppermint",
    "pink-pepper": "Pink Pepper",
    "rose": "Rose",
    "rosemary": "Rosemary",
    "sandalwood": "Sandalwood",
    "spruce": "Spruce",
    "tea-tree": "Tea Tree",
    "thyme": "Thyme",
    "vetiver": "Vetiver",
    "ylang-ylang": "Ylang-Ylang",
}


async def main() -> None:
    updated = 0
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AromaCardModel).where(AromaCardModel.category == "aroma")
        )
        for model in result.scalars():
            payload = dict(model.payload or {})
            existing = str(payload.get("name_en") or "").strip()
            name_ru = str(payload.get("name_ru") or "").strip()
            # Skip if already has a distinct English name
            if existing and existing != name_ru and existing != model.name:
                continue
            en = SLUG_TO_EN.get(model.slug)
            if not en:
                log.warning("No mapping for slug=%s", model.slug)
                continue
            payload["name_en"] = en
            model.payload = payload
            updated += 1
            log.info("  %s → %s", model.slug, en)
        await session.commit()
    log.info("Updated %d aroma cards with name_en", updated)


if __name__ == "__main__":
    asyncio.run(main())
