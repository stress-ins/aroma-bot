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
    "bay-laurel": "Bay Laurel",
    "benzoin": "Benzoin",
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
    "mandarin": "Mandarin",
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

# Cards where model.name is in English — need Russian name in payload
SLUG_TO_RU: dict[str, str] = {
    "blue-tansy": "Голубая пижма",
}


async def main() -> None:
    updated_en = 0
    updated_ru = 0
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AromaCardModel).where(AromaCardModel.category == "aroma")
        )
        for model in result.scalars():
            payload = dict(model.payload or {})
            changed = False

            # Fill name_en from SLUG_TO_EN
            existing_en = str(payload.get("name_en") or "").strip()
            name_ru = str(payload.get("name_ru") or "").strip()
            if not (existing_en and existing_en != name_ru and existing_en != model.name):
                en = SLUG_TO_EN.get(model.slug)
                if en:
                    payload["name_en"] = en
                    changed = True
                    updated_en += 1
                    log.info("  name_en: %s → %s", model.slug, en)
                else:
                    log.warning("No EN mapping for slug=%s", model.slug)

            # Fill name_ru from SLUG_TO_RU (for cards with English model.name)
            ru = SLUG_TO_RU.get(model.slug)
            if ru and name_ru != ru:
                payload["name_ru"] = ru
                changed = True
                updated_ru += 1
                log.info("  name_ru: %s → %s", model.slug, ru)

            if changed:
                model.payload = payload

        await session.commit()
    log.info("Updated %d name_en, %d name_ru", updated_en, updated_ru)


if __name__ == "__main__":
    asyncio.run(main())
