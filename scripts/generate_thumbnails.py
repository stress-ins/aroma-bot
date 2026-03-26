#!/usr/bin/env python3
"""One-time backfill: generate thumbnails for existing carousel and reels images.

Run on VPS:
    cd /opt/aroma && .venv/bin/python scripts/generate_thumbnails.py

Idempotent — skips images that already have thumbnails.
"""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.services.image_thumbs import ensure_thumbnails


def main():
    data_dir = Path(__file__).resolve().parent.parent / "data"
    dirs = [
        data_dir / "carousel_assets",
        data_dir / "reels_assets",
        data_dir / "thumbnails",
    ]

    total = 0
    generated = 0
    skipped = 0
    errors = 0

    for base in dirs:
        if not base.exists():
            continue
        for img_path in sorted(base.rglob("*.png")):
            if "_thumb" in img_path.stem or "_lqip" in img_path.stem:
                continue
            total += 1
            thumb_path = img_path.parent / f"{img_path.stem}_thumb.webp"
            if thumb_path.exists():
                skipped += 1
                continue
            result = ensure_thumbnails(img_path)
            if result[0]:
                generated += 1
                print(f"  ✓ {img_path.relative_to(data_dir)}")
            else:
                errors += 1
                print(f"  ✗ {img_path.relative_to(data_dir)}")

    print(f"\nDone: {total} images, {generated} generated, {skipped} skipped, {errors} errors")


if __name__ == "__main__":
    main()
