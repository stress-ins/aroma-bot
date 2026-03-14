"""Tests for image quality — detects white stripe artifacts in generated and source images."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _detect_white_stripes(
    image_path: Path | str,
    threshold: float = 0.95,
    min_run: int = 5,
    min_span_ratio: float = 0.15,
) -> dict:
    """Detect horizontal/vertical white stripe artifacts in an image.

    Args:
        image_path: Path to the image file.
        threshold: Fraction of pixels in a row/col that must be white (≥245/255).
        min_run: Minimum consecutive white rows/cols to count as a stripe.
        min_span_ratio: Stripe must span at least this fraction of image height/width.

    Returns:
        {"has_stripes": bool, "row_stripes": list[tuple], "col_stripes": list[tuple]}
    """
    try:
        from PIL import Image
        import numpy as np
    except ImportError:
        pytest.skip("PIL/numpy not available for image quality tests")

    img = Image.open(image_path).convert("RGB")
    arr = np.array(img, dtype=np.float32) / 255.0  # H × W × 3

    height, width = arr.shape[:2]

    def _find_stripes(values: list[bool], min_run: int, min_span_ratio: float, total: int) -> list[tuple]:
        stripes = []
        start = None
        for i, is_white in enumerate(values):
            if is_white and start is None:
                start = i
            elif not is_white and start is not None:
                run_len = i - start
                if run_len >= min_run and run_len / total >= min_span_ratio:
                    stripes.append((start, i - 1, run_len))
                start = None
        if start is not None:
            run_len = len(values) - start
            if run_len >= min_run and run_len / total >= min_span_ratio:
                stripes.append((start, len(values) - 1, run_len))
        return stripes

    # Check rows (horizontal stripes)
    row_white = [
        float(np.mean(arr[r, :, :].min(axis=-1) >= threshold)) >= threshold
        for r in range(height)
    ]
    row_stripes = _find_stripes(row_white, min_run, min_span_ratio, height)

    # Check columns (vertical stripes)
    col_white = [
        float(np.mean(arr[:, c, :].min(axis=-1) >= threshold)) >= threshold
        for c in range(width)
    ]
    col_stripes = _find_stripes(col_white, min_run, min_span_ratio, width)

    return {
        "has_stripes": bool(row_stripes or col_stripes),
        "row_stripes": row_stripes,
        "col_stripes": col_stripes,
    }


# ---------------------------------------------------------------------------
# Test 1: detector function works on synthetic images
# ---------------------------------------------------------------------------

def test_white_stripe_detector_detects_stripes():
    """Detector correctly identifies a white horizontal band in a synthetic image."""
    try:
        from PIL import Image
        import numpy as np
    except ImportError:
        pytest.skip("PIL/numpy not available")

    import tempfile, os

    # Create an image with a white horizontal stripe in the middle
    height, width = 100, 200
    arr = np.zeros((height, width, 3), dtype=np.uint8)
    arr[40:60, :, :] = 255  # white band from row 40 to 59 (20 rows = 20% of height)

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        tmp_path = f.name

    try:
        Image.fromarray(arr).save(tmp_path)
        result = _detect_white_stripes(tmp_path, min_run=5, min_span_ratio=0.15)
        assert result["has_stripes"] is True, "Should detect the white stripe"
        assert len(result["row_stripes"]) >= 1
    finally:
        os.unlink(tmp_path)


def test_white_stripe_detector_no_false_positive():
    """Detector does not flag a normal gradient image as having stripes."""
    try:
        from PIL import Image
        import numpy as np
    except ImportError:
        pytest.skip("PIL/numpy not available")

    import tempfile, os

    height, width = 100, 200
    # Create a gradient image (no solid white stripe)
    arr = np.zeros((height, width, 3), dtype=np.uint8)
    for r in range(height):
        # Gradient from dark to medium gray
        val = int(r / height * 200)
        arr[r, :, :] = val

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        tmp_path = f.name

    try:
        Image.fromarray(arr).save(tmp_path)
        result = _detect_white_stripes(tmp_path)
        assert result["has_stripes"] is False, "Should not flag a gradient image"
    finally:
        os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# Test 2: no white stripes in reference images (if any exist)
# ---------------------------------------------------------------------------

def test_no_white_stripes_in_reference_images():
    """All reference images in assets/reference_images/ must not have white stripe artifacts."""
    try:
        from PIL import Image
        import numpy as np
    except ImportError:
        pytest.skip("PIL/numpy not available")

    images_dir = ROOT / "assets" / "reference_images"
    if not images_dir.exists():
        pytest.skip("No reference_images directory found")

    image_files = list(images_dir.rglob("*.jpg")) + list(images_dir.rglob("*.png"))
    if not image_files:
        pytest.skip("No image files found in reference_images/")

    failures = []
    for img_path in image_files:
        try:
            # Use stricter min_span_ratio=0.25 to avoid false positives from natural
            # white regions in reference photos (white bottles, clear oils, etc.)
            result = _detect_white_stripes(img_path, min_run=10, min_span_ratio=0.25)
            if result["has_stripes"]:
                failures.append(
                    f"{img_path.name}: row_stripes={result['row_stripes']}, col_stripes={result['col_stripes']}"
                )
        except Exception as e:
            failures.append(f"{img_path.name}: error reading image: {e}")

    assert not failures, (
        f"White stripe artifacts found in {len(failures)} image(s):\n" + "\n".join(failures)
    )
