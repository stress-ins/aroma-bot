"""Validate uploaded images: format, size, resolution, blur, brightness."""

from __future__ import annotations

import io
from dataclasses import dataclass, field

from PIL import Image


@dataclass
class ValidationResult:
    ok: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    width: int = 0
    height: int = 0
    format: str = ""

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "errors": self.errors,
            "warnings": self.warnings,
            "width": self.width,
            "height": self.height,
            "format": self.format,
        }


ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
MAX_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
MIN_DIMENSION = 800
MAX_ASPECT_RATIO = 3.0  # warn if wider/taller than 3:1

# Blur: Laplacian variance threshold (lower = blurrier)
BLUR_THRESHOLD = 50.0
# Brightness: mean pixel value
MIN_BRIGHTNESS = 30
MAX_BRIGHTNESS = 225


def validate_uploaded_photo(image_bytes: bytes) -> ValidationResult:
    """Run all validation checks on uploaded image bytes."""
    result = ValidationResult()

    # Size check
    if len(image_bytes) > MAX_SIZE_BYTES:
        mb = len(image_bytes) / (1024 * 1024)
        result.ok = False
        result.errors.append(f"Файл слишком большой: {mb:.1f} МБ (макс. 10 МБ)")
        return result

    # Format + dimensions
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img.load()  # force decode
    except Exception:
        result.ok = False
        result.errors.append("Не удалось открыть файл как изображение")
        return result

    fmt = (img.format or "").upper()
    result.format = fmt
    result.width, result.height = img.size

    if fmt not in ALLOWED_FORMATS:
        result.ok = False
        result.errors.append(f"Формат {fmt or 'неизвестный'} не поддерживается (нужен JPEG, PNG или WebP)")
        return result

    # Resolution
    if result.width < MIN_DIMENSION or result.height < MIN_DIMENSION:
        result.ok = False
        result.errors.append(
            f"Разрешение {result.width}×{result.height} слишком низкое (мин. {MIN_DIMENSION}×{MIN_DIMENSION})"
        )

    # Aspect ratio
    ratio = max(result.width, result.height) / max(min(result.width, result.height), 1)
    if ratio > MAX_ASPECT_RATIO:
        result.warnings.append(f"Необычное соотношение сторон ({ratio:.1f}:1) — фото может обрезаться")

    # Quality checks (blur + brightness) via numpy if available
    try:
        _check_quality(img, result)
    except ImportError:
        pass  # numpy not available — skip quality checks

    return result


def _check_quality(img: Image.Image, result: ValidationResult) -> None:
    """Check blur (Laplacian) and brightness (mean luminance)."""
    import numpy as np

    # Convert to grayscale numpy array
    gray = img.convert("L")
    arr = np.asarray(gray, dtype=np.float64)

    # Brightness: mean pixel value
    mean_brightness = float(arr.mean())
    if mean_brightness < MIN_BRIGHTNESS:
        result.warnings.append(f"Фото слишком тёмное (яркость {mean_brightness:.0f}/255)")
    elif mean_brightness > MAX_BRIGHTNESS:
        result.warnings.append(f"Фото слишком светлое / пересвечено (яркость {mean_brightness:.0f}/255)")

    # Blur: Laplacian variance
    # Manual 3x3 Laplacian convolution (avoids scipy/cv2 dependency)
    if arr.shape[0] >= 3 and arr.shape[1] >= 3:
        laplacian = (
            -arr[:-2, 1:-1] - arr[2:, 1:-1]
            - arr[1:-1, :-2] - arr[1:-1, 2:]
            + 4 * arr[1:-1, 1:-1]
        )
        variance = float(laplacian.var())
        if variance < BLUR_THRESHOLD:
            result.warnings.append(f"Фото может быть размытым (чёткость {variance:.0f}, мин. {BLUR_THRESHOLD:.0f})")
