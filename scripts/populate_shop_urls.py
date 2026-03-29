"""One-time script: populate shop_url in aroma card payloads.

Links to ifeelaromalab.ru products (Compagnie des Sens, VosHuiles).
Young Living excluded — promo code AROMARA has limited applicability.
"""

import asyncio
import logging

from sqlalchemy import select

from db.models import AromaCardModel
from db.session import AsyncSessionLocal

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

BASE = "https://ifeelaromalab.ru"

# slug → shop product path (prefer Compagnie des Sens over VosHuiles)
SHOP_URLS: dict[str, str] = {
    "orange": f"{BASE}/product/compagnie-des-sens-apelsin-orange-30-ml",
    "basil": f"{BASE}/product/compagnie-des-sens-bazilik-basil-10-ml",
    "bergamot": f"{BASE}/product/compagnie-des-sens-bergamot-bergamot-10-ml",
    "helichrysum": f"{BASE}/product/compagnie-des-sens-bessmertnik-helichrysum-5-ml",
    "vetiver": f"{BASE}/product/compagnie-des-sens-vetiver-vetiver-5-ml",
    "clove": f"{BASE}/product/compagnie-des-sens-gvozdika-clove-10-ml",
    "geranium": f"{BASE}/product/compagnie-des-sens-geran-geranium-10-ml",
    "grapefruit": f"{BASE}/product/compagnie-des-sens-greypfrut-grapefruit-10-ml",
    "spruce": f"{BASE}/product/compagnie-des-sens-chernaya-el-black-spruce-10-ml",
    "ylang-ylang": f"{BASE}/product/compagnie-des-sens-ilan-ilang-ylang-ylang-10-ml",
    "ginger": f"{BASE}/product/compagnie-des-sens-imbir-ginger-10-ml",
    "cedarwood": f"{BASE}/product/compagnie-des-sens-kedr-cedarwood-30-ml",
    "cypress": f"{BASE}/product/compagnie-des-sens-kiparis-cypress-10-ml",
    "cinnamon": f"{BASE}/product/compagnie-des-sens-koritsa-cinnamon-bark-10-ml",
    "lavender": f"{BASE}/product/compagnie-des-sens-lavanda-lavender-10-ml",
    "frankincense": f"{BASE}/product/compagnie-des-sens-ladan-frankincense-5-ml",
    "lemongrass": f"{BASE}/product/compagnie-des-sens-lemongrass-lemongrass-30-ml",
    "lemon": f"{BASE}/product/compagnie-des-sens-limon-lemon-30-ml",
    "marjoram": f"{BASE}/product/compagnie-des-sens-mayoran-marjoram-10-ml",
    "mandarin": f"{BASE}/product/compagnie-des-sens-mandarin-tangerine-10-ml",
    "juniper": f"{BASE}/product/compagnie-des-sens-mozhzhevelnik-juniper-10-ml",
    "clary-sage": f"{BASE}/product/cds-shalfey-muskatnyy-clary-sage-10-ml",
    "peppermint": f"{BASE}/product/compagnie-des-sens-myata-perechnaya-peppermint-30-ml",
    "neroli": f"{BASE}/product/cds-neroli-neroli-5-ml",
    "oregano": f"{BASE}/product/compagnie-des-sens-oregano-oregano-10-ml",
    "patchouli": f"{BASE}/product/compagnie-des-sens-pachuli-patchouli-10-ml",
    "balsam-fir": f"{BASE}/product/compagnie-des-sens-balzamicheskaya-pihta-balsam-fir-10-ml",
    "rosemary": f"{BASE}/product/compagnie-des-sens-rozmarin-rosemary-10-ml",
    "german-chamomile": f"{BASE}/product/cds-nemetska-romashka-german-chamomile-5-ml",
    "eucalyptus-globulus": f"{BASE}/product/compagnie-des-sens-evkalipt-sharovidnyy-eucalyptus-globulus-30-ml",
    "tea-tree": f"{BASE}/product/compagnie-des-sens-chaynoe-derevo-tea-tree-30ml",
    "black-pepper": f"{BASE}/product/compagnie-des-sens-chernyy-perets-black-pepper-10-ml",
    # VosHuiles (oils not available at CdS)
    "jasmine": f"{BASE}/product/voshuiles-efirnoe-maslo-zhasmia-krupnotsvetkovogo-jasmine-grandiflorum-2-ml",
    "rose": f"{BASE}/product/voshuiles-efirnoe-maslo-damasskoy-rozy-rose-damas-1-ml",
}

# Oils without a match in the shop (non-YL):
# cassia, blue-spruce, copaiba, kunzea, lime, sandalwood, thyme,
# fennel, citronella, grapefruit — already mapped above


async def main() -> None:
    updated = 0
    skipped = 0
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AromaCardModel).where(AromaCardModel.category == "aroma")
        )
        cards = result.scalars().all()
        for card in cards:
            url = SHOP_URLS.get(card.slug)
            if not url:
                skipped += 1
                continue
            if card.payload.get("shop_url") == url:
                skipped += 1
                continue
            card.payload["shop_url"] = url
            # Mark payload as dirty for MutableDict
            card.payload.changed()
            updated += 1
            log.info(f"  ✓ {card.slug} → {url}")
        await session.commit()
    log.info(f"\nDone: {updated} updated, {skipped} skipped")


if __name__ == "__main__":
    asyncio.run(main())
