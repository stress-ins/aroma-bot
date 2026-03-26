"""Thumbnail and LQIP generation for progressive image loading.

Generates two derivative images alongside any original:
- **thumb** (300px wide, WebP, ~15-30 KB): for grids, version lists, hero strips
- **lqip** (32px wide, WebP, ~1-2 KB): for blur-up placeholder

Usage::

    from bot.services.image_thumbs import ensure_thumbnails, thumb_urls

    # After saving an image file:
    ensure_thumbnails(path_to_image)

    # Get URLs for frontend:
    urls = thumb_urls("/generated/carousel_assets/abc/slide_1.png")
    # => {"thumb_url": "...slide_1_thumb.webp", "lqip_url": "...slide_1_lqip.webp"}
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

THUMB_WIDTH = 300
LQIP_WIDTH = 32
THUMB_QUALITY = 80
LQIP_QUALITY = 50


def ensure_thumbnails(image_path: str | Path) -> tuple[str, str]:
    """Generate thumb + LQIP for an image if they don't already exist.

    Returns (thumb_path, lqip_path) as strings, or ("", "") on failure.
    """
    src = Path(image_path)
    if not src.exists():
        return ("", "")

    stem = src.stem
    directory = src.parent
    thumb_path = directory / f"{stem}_thumb.webp"
    lqip_path = directory / f"{stem}_lqip.webp"

    # Skip if both already exist
    if thumb_path.exists() and lqip_path.exists():
        return (str(thumb_path), str(lqip_path))

    try:
        from PIL import Image

        with Image.open(src) as img:
            # Convert RGBA to RGB for WebP (avoid transparency issues)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")

            w, h = img.size

            # Thumb (300px wide)
            if not thumb_path.exists():
                ratio = THUMB_WIDTH / w
                thumb = img.resize(
                    (THUMB_WIDTH, max(1, int(h * ratio))),
                    Image.Resampling.LANCZOS,
                )
                thumb.save(thumb_path, "WEBP", quality=THUMB_QUALITY)

            # LQIP (32px wide)
            if not lqip_path.exists():
                ratio = LQIP_WIDTH / w
                lqip = img.resize(
                    (LQIP_WIDTH, max(1, int(h * ratio))),
                    Image.Resampling.LANCZOS,
                )
                lqip.save(lqip_path, "WEBP", quality=LQIP_QUALITY)

        logger.debug("Thumbnails generated for %s", src.name)
        return (str(thumb_path), str(lqip_path))

    except Exception:
        logger.warning("Failed to generate thumbnails for %s", src, exc_info=True)
        return ("", "")


def thumb_urls(original_url: str) -> dict[str, str]:
    """Derive thumb/lqip URLs from an original image URL.

    Works by replacing the extension with ``_thumb.webp`` / ``_lqip.webp``.

    >>> thumb_urls("/generated/carousel_assets/abc/slide_1_de34.png")
    {"thumb_url": "/generated/carousel_assets/abc/slide_1_de34_thumb.webp",
     "lqip_url": "/generated/carousel_assets/abc/slide_1_de34_lqip.webp"}
    """
    if not original_url:
        return {"thumb_url": "", "lqip_url": ""}

    # Remove extension, add suffix
    dot = original_url.rfind(".")
    if dot == -1:
        base = original_url
    else:
        base = original_url[:dot]

    return {
        "thumb_url": f"{base}_thumb.webp",
        "lqip_url": f"{base}_lqip.webp",
    }


def enrich_image_dict(img: dict, url_key: str = "url") -> dict:
    """Add thumb_url and lqip_url to an image dict if missing.

    Non-destructive: returns the same dict with added keys.
    """
    if not img or not isinstance(img, dict):
        return img

    url = img.get(url_key, "")
    if url and not img.get("thumb_url"):
        urls = thumb_urls(url)
        img["thumb_url"] = urls["thumb_url"]
        img["lqip_url"] = urls["lqip_url"]

    return img
