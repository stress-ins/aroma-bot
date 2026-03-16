"""Download botanical images from Wikimedia Commons for aroma cards missing images.

Usage:
    .venv/bin/python scripts/download_wikimedia_images.py [--dry-run] [--category aroma]

Downloads free-licensed images from Wikimedia Commons API (no API key needed).
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

IMAGES_DIR = ROOT / "assets" / "reference_images"
WIKIMEDIA_API = "https://commons.wikimedia.org/w/api.php"

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Map slug -> English search term for Wikimedia Commons
SEARCH_TERMS: dict[str, str] = {
    "angelica": "Angelica archangelica plant",
    "bay-laurel": "Laurus nobilis leaves",
    "benzoin": "Styrax benzoin resin",
    "black-spruce": "Picea mariana tree",
    "blue-tansy": "Tanacetum annuum flower",
    "caraway": "Carum carvi seeds",
    "carrot-seed": "Daucus carota flower",
    "cistus": "Cistus ladanifer flower",
    "davana": "Artemisia pallens plant",
    "elemi": "Canarium luzonicum resin",
    "eucaliptus-blue": "Eucalyptus globulus leaves",
    "fragonia": "Agonis fragrans flower",
    "ho-wood": "Cinnamomum camphora tree",
    "hong-kuai": "Chamaecyparis formosensis",
    "hyssop": "Hyssopus officinalis flower",
    "laurus": "Laurus nobilis branch",
    "ledum": "Ledum palustre flower",
    "manuka": "Leptospermum scoparium flower",
    "melissa": "Melissa officinalis plant",
    "myrrh": "Commiphora myrrha resin",
    "myrtle": "Myrtus communis flower",
    "nutmeg": "Myristica fragrans fruit",
    "palmarosa": "Cymbopogon martinii grass",
    "palo-santo": "Bursera graveolens wood",
    "petitgrain": "Citrus aurantium leaves",
    "pine": "Pinus sylvestris needles",
    "pink-pepper": "Schinus molle berries",
    "ravintsara": "Cinnamomum camphora leaf",
    "roman-chamomile": "Chamaemelum nobile flower",
    "spearmint": "Mentha spicata leaves",
    "valerian": "Valeriana officinalis flower",
    "wintergreen": "Gaultheria procumbens berries",
}


async def search_wikimedia(query: str, client: httpx.AsyncClient) -> str | None:
    """Search Wikimedia Commons for an image and return the direct URL."""
    # Step 1: Search for files
    resp = await client.get(
        WIKIMEDIA_API,
        params={
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrnamespace": "6",  # File namespace
            "gsrsearch": query,
            "gsrlimit": "5",
            "prop": "imageinfo",
            "iiprop": "url|size|mime",
            "iiurlwidth": "800",
        },
        timeout=30,
    )
    if resp.status_code != 200:
        logger.warning("  Wikimedia API returned %d for: %s", resp.status_code, query)
        return None
    data = resp.json()
    pages = data.get("query", {}).get("pages", {})
    if not pages:
        return None

    # Filter: prefer JPEG/PNG, reasonable size, landscape/square
    candidates = []
    for page in pages.values():
        info_list = page.get("imageinfo", [])
        if not info_list:
            continue
        info = info_list[0]
        mime = info.get("mime", "")
        width = info.get("width", 0)
        height = info.get("height", 0)
        if mime not in ("image/jpeg", "image/png"):
            continue
        if width < 400 or height < 300:
            continue
        # Prefer thumbnail URL (resized to 800px width)
        thumb_url = info.get("thumburl") or info.get("url")
        candidates.append((width * height, thumb_url))

    if not candidates:
        return None

    # Return the largest candidate
    candidates.sort(reverse=True)
    return candidates[0][1]


async def download_image(url: str, dest: Path, client: httpx.AsyncClient) -> bool:
    """Download image to destination path."""
    try:
        resp = await client.get(url, timeout=30, follow_redirects=True)
        if resp.status_code != 200:
            return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(resp.content)
        return True
    except Exception as exc:
        logger.error("  Download failed: %s", exc)
        return False


async def main(dry_run: bool = False, category: str = "aroma") -> None:
    from db.session import AsyncSessionLocal
    from sqlalchemy import select
    from db.models import AromaCardModel

    # Find cards that need images
    async with AsyncSessionLocal() as session:
        q = select(AromaCardModel).filter(AromaCardModel.category == category)
        result = await session.execute(q)
        rows = result.scalars().all()

    needs_image = []
    for r in rows:
        slug = r.slug
        cat_dir = IMAGES_DIR / f"{category}s"
        existing = list(cat_dir.glob(f"{slug}.*")) if cat_dir.exists() else []
        if not existing and slug in SEARCH_TERMS:
            needs_image.append((slug, r.name, SEARCH_TERMS[slug]))

    logger.info("Found %d %s cards needing images (with search terms)", len(needs_image), category)

    if dry_run:
        for slug, name, term in needs_image:
            logger.info("  [DRY-RUN] %s (%s) -> search: %s", slug, name, term)
        return

    downloaded = 0
    failed = []

    headers = {
        "User-Agent": "AromaBot/1.0 (aromatherapy reference; contact: info@aromara.ru)",
    }
    async with httpx.AsyncClient(headers=headers) as client:
        for slug, name, search_term in needs_image:
            logger.info("Searching: %s (%s)...", slug, search_term)
            url = await search_wikimedia(search_term, client)

            if not url:
                logger.warning("  No image found for %s", slug)
                failed.append(slug)
                continue

            # Determine extension from URL
            ext = "jpg"
            if ".png" in url.lower():
                ext = "png"

            dest = IMAGES_DIR / f"{category}s" / f"{slug}.{ext}"
            ok = await download_image(url, dest, client)

            if ok:
                downloaded += 1
                logger.info("  Downloaded: %s (%d KB)", dest.name, dest.stat().st_size // 1024)
            else:
                failed.append(slug)

            # Be respectful to Wikimedia
            await asyncio.sleep(2)

    logger.info("\nDone: %d downloaded, %d failed", downloaded, len(failed))
    if failed:
        logger.info("Failed: %s", ", ".join(failed))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--category", default="aroma")
    args = parser.parse_args()
    asyncio.run(main(dry_run=args.dry_run, category=args.category))
