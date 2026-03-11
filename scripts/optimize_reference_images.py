from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parents[1]
IMAGES_DIR = ROOT / "assets" / "reference_images"
MAX_DIMENSION = 1200
JPEG_QUALITY = 76


def optimize_image(path: Path) -> tuple[int, int] | None:
    before = path.stat().st_size
    suffix = path.suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
        return None

    with Image.open(path) as img:
        image = ImageOps.exif_transpose(img)
        if image.mode not in {"RGB", "RGBA"}:
            image = image.convert("RGBA" if "A" in image.getbands() else "RGB")

        width, height = image.size
        largest = max(width, height)
        if largest > MAX_DIMENSION:
            scale = MAX_DIMENSION / largest
            image = image.resize((int(width * scale), int(height * scale)), Image.Resampling.LANCZOS)

        save_kwargs: dict[str, object] = {"optimize": True}
        if suffix in {".jpg", ".jpeg"}:
            if image.mode != "RGB":
                image = image.convert("RGB")
            save_kwargs.update({"quality": JPEG_QUALITY, "progressive": True})
        elif suffix == ".png":
            save_kwargs.update({"compress_level": 9})
        elif suffix == ".webp":
            save_kwargs.update({"quality": 78, "method": 6})

        image.save(path, **save_kwargs)

    after = path.stat().st_size
    return before, after


def main() -> int:
    optimized = 0
    total_before = 0
    total_after = 0

    for path in sorted(IMAGES_DIR.rglob("*")):
        if not path.is_file():
            continue
        try:
            result = optimize_image(path)
        except Exception:
            continue
        if result is None:
            continue
        before, after = result
        optimized += 1
        total_before += before
        total_after += after
        print(f"{path.relative_to(ROOT)}: {before} -> {after}")

    saved = total_before - total_after
    print(f"optimized {optimized} files")
    print(f"saved {saved} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
