"""Trim whitespace and fix composite (bottle+plant) oil images.

Usage:
    .venv/bin/python scripts/fix_oil_images.py [--dry-run] [DIR]

Default DIR: assets/reference_images/aromas/

Fixes two types of image issues:
1. Composite images (w/h > 1.6): wide "bottle + plant" shots — keep right 65% (the plant side)
2. Excess whitespace on edges — trim to content with small padding
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIR = ROOT / "assets" / "reference_images" / "aromas"


def trim_whitespace(img, padding: int = 6, threshold: int = 240):
    """Trim whitespace borders, keeping a small padding around content."""
    try:
        from PIL import Image, ImageChops
    except ImportError:
        print("ERROR: Pillow not installed. Run: pip install Pillow")
        sys.exit(1)

    rgb = img.convert("RGB")
    bg = Image.new("RGB", rgb.size, (255, 255, 255))
    diff = ImageChops.difference(rgb, bg)
    bbox = diff.getbbox()
    if not bbox:
        return img
    w, h = img.size
    left = max(0, bbox[0] - padding)
    top = max(0, bbox[1] - padding)
    right = min(w, bbox[2] + padding)
    bottom = min(h, bbox[3] + padding)
    return img.crop((left, top, right, bottom))


def fix_composite(img):
    """Wide images (bottle+plant): keep right 65% (the plant side)."""
    w, h = img.size
    if w / h > 1.6:
        img = img.crop((int(w * 0.35), 0, w, h))
    return img


def needs_fix(img, threshold: int = 240) -> tuple[bool, str | None]:
    """Check if an image needs fixing. Returns (needs_fix, reason)."""
    w, h = img.size
    if w / h > 1.6:
        return True, "composite"

    rgb = img.convert("RGB")
    # Check edges for excess whitespace (first 10 pixels from each side)
    check_cols = min(10, w)
    check_rows = min(10, h)

    left_col = [rgb.getpixel((x, h // 2)) for x in range(check_cols)]
    right_col = [rgb.getpixel((w - 1 - x, h // 2)) for x in range(check_cols)]
    bottom_row = [rgb.getpixel((w // 2, h - 1 - y)) for y in range(check_rows)]

    def _all_white(pixels) -> bool:
        return all(all(c > threshold for c in p) for p in pixels)

    if _all_white(left_col) or _all_white(right_col) or _all_white(bottom_row):
        return True, "whitespace"

    return False, None


def process(path: Path, dry_run: bool = False) -> bool:
    """Process a single image. Returns True if image was (or would be) fixed."""
    try:
        from PIL import Image
    except ImportError:
        print("ERROR: Pillow not installed. Run: pip install Pillow")
        sys.exit(1)

    img = Image.open(path)
    flag, reason = needs_fix(img)
    if not flag:
        return False

    orig_size = img.size
    img = fix_composite(img)
    img = trim_whitespace(img)

    if not dry_run:
        # Preserve format based on extension
        save_kwargs: dict = {"optimize": True}
        if path.suffix.lower() in (".jpg", ".jpeg"):
            save_kwargs["quality"] = 92
        img.save(path, **save_kwargs)

    prefix = "[dry-run] " if dry_run else ""
    print(f"  {prefix}Fixed ({reason}): {path.name}  {orig_size[0]}x{orig_size[1]} → {img.size[0]}x{img.size[1]}")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Fix composite and whitespace-heavy oil images")
    parser.add_argument("dir", nargs="?", type=Path, default=DEFAULT_DIR, help="Directory to scan (default: assets/reference_images/aromas/)")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without saving")
    args = parser.parse_args()

    images_dir: Path = args.dir
    if not images_dir.exists():
        print(f"ERROR: directory not found: {images_dir}")
        sys.exit(1)

    image_files = sorted(
        p for p in images_dir.iterdir()
        if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")
    )
    if not image_files:
        print(f"No images found in {images_dir}")
        return

    print(f"Scanning {len(image_files)} images in {images_dir}" + (" [DRY RUN]" if args.dry_run else ""))
    fixed = 0
    for path in image_files:
        if process(path, dry_run=args.dry_run):
            fixed += 1

    if fixed == 0:
        print("All images look good — nothing to fix.")
    else:
        action = "Would fix" if args.dry_run else "Fixed"
        print(f"\n{action} {fixed}/{len(image_files)} images.")


if __name__ == "__main__":
    main()
