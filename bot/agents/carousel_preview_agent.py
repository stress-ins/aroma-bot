"""Carousel Preview Agent — Vision-based text placement + PNG rendering."""
from __future__ import annotations

import base64
import io
import json
import logging
from pathlib import Path

from bot.services.drafts_store import get_draft, update_draft
from bot.services.carousel_assets import load_carousel_slide_images
from bot.services.claude_client import call_claude

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────
SLIDE_ROLES = ["hook", "problem", "mechanism", "insight", "solution", "cta"]
ROLE_PLACEMENT_PREFS: dict[str, str] = {
    "hook": "bottom",
    "problem": "center",
    "mechanism": "center",
    "insight": "center",
    "solution": "bottom",
    "cta": "bottom-center",
}

_FONT_PATH = Path(__file__).parent.parent.parent / "assets" / "fonts" / "DeldedaOpen.ttf"
_CORRECTIONS_LOG = Path(__file__).parent.parent.parent / "data" / "placement_corrections_log.jsonl"


# ── 1. Analyze text placement via Claude Vision ───────────────────────────────

def _zone_brightness(img_bytes: bytes, top_frac: float, h_frac: float) -> float:
    """Return mean brightness (0-255) of a horizontal strip of the image."""
    from PIL import Image, ImageStat
    img = Image.open(io.BytesIO(img_bytes)).convert("L")
    w, h = img.size
    y0 = int(h * top_frac)
    y1 = int(h * min(top_frac + h_frac, 1.0))
    return ImageStat.Stat(img.crop((0, y0, w, y1))).mean[0]


def analyze_text_placement(
    img_bytes: bytes,
    slide_index: int,
    bias: dict | None = None,
) -> dict:
    """Use Claude Vision to find optimal text zone on a slide image.

    Returns dict with keys: top, left, width, height, text_color, text_align, role, source.
    """
    from bot.handlers.carousel import _find_text_zone

    role = SLIDE_ROLES[slide_index] if slide_index < len(SLIDE_ROLES) else "unknown"
    preferred = ROLE_PLACEMENT_PREFS.get(role)

    logger.info("Using heuristic for slide %d (role=%s, preferred=%s)", slide_index, role, preferred)
    top_frac, h_frac = _find_text_zone(img_bytes, preferred_zone=preferred)

    # Determine text_color from zone brightness
    brightness = _zone_brightness(img_bytes, top_frac, h_frac)
    text_color = "dark" if brightness > 160 else "light"

    # Determine text alignment by role
    text_align = "center" if role in ("hook", "cta") else "left"

    placement = {
        "top": top_frac,
        "left": 0.08,
        "width": 0.84,
        "height": h_frac,
        "text_color": text_color,
        "text_align": text_align,
        "role": role,
        "source": "heuristic",
    }
    # Apply bias from correction history
    if bias:
        for key in ("top", "left", "width", "height"):
            if key in bias:
                placement[key] = max(0.0, min(1.0, placement[key] + float(bias[key])))
    return placement


# ── 1b. Analyze reels text placement via Claude Vision ───────────────────

_REELS_PLACEMENT_FALLBACK: dict = {
    "placement": {"zone": "top", "x_percent": 10, "y_percent": 8, "max_width_percent": 80},
    "typography": {"color_hex": "#FFFFFF", "shadow_color": "rgba(0,0,0,0.7)", "font_size_px": 18, "font_weight": 700},
}


def analyze_reels_placement(img_bytes: bytes) -> dict:
    """Use Claude Vision to find optimal text placement on a 9:16 reels frame."""
    # TEMP: Vision API disabled — use fallback only (re-enable when Gemini vision is verified)
    logger.info("Vision API disabled for reels, using fallback placement")
    return dict(_REELS_PLACEMENT_FALLBACK)


# ── 2. Render preview PNG ─────────────────────────────────────────────────────

def render_preview_png(
    img_bytes: bytes,
    text: str,
    placement: dict,
    size: tuple[int, int] = (1080, 1350),
) -> bytes:
    """Render editorial-style preview PNG: stroked typography on clean image."""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
    target_w, target_h = size

    src_w, src_h = img.size
    src_ratio = src_w / src_h
    tgt_ratio = target_w / target_h
    if src_ratio > tgt_ratio:
        new_h = target_h
        new_w = int(src_w * target_h / src_h)
    else:
        new_w = target_w
        new_h = int(src_h * target_w / src_w)
    img = img.resize((new_w, new_h), Image.LANCZOS)
    lc = (new_w - target_w) // 2
    tc = (new_h - target_h) // 2
    img = img.crop((lc, tc, lc + target_w, tc + target_h))

    w, h = size

    box_left   = int(w * placement.get("left",   0.06))
    box_top    = int(h * placement.get("top",    0.58))
    box_w      = int(w * placement.get("width",  0.88))
    box_h      = int(h * placement.get("height", 0.32))
    box_right  = box_left + box_w
    box_bottom = box_top  + box_h

    # Adaptive gradient for text readability
    top_frac = placement.get("top", 0.58)
    text_color_key = placement.get("text_color", "light")
    text_align = placement.get("text_align", "left")

    if text_color_key != "dark":
        # Only apply gradient when text is light (zone is dark enough for white text)
        gradient = Image.new("RGBA", img.size, (0, 0, 0, 0))
        grad_draw = ImageDraw.Draw(gradient)

        if top_frac < 0.33:
            # Top-down gradient (text at top)
            grad_bottom = min(h, box_bottom + 40)
            grad_h = grad_bottom
            for i in range(grad_h):
                progress = 1.0 - (i / grad_h)
                alpha = int(160 * progress ** 1.5)
                grad_draw.line([(0, i), (w, i)], fill=(0, 0, 0, min(alpha, 160)))
        elif top_frac > 0.55:
            # Bottom-up gradient (text at bottom — original behavior)
            grad_top = max(0, box_top - 40)
            grad_h = box_bottom - grad_top
            for i in range(grad_h):
                alpha = int(160 * (i / grad_h) ** 1.5)
                grad_draw.line(
                    [(0, grad_top + i), (w, grad_top + i)],
                    fill=(0, 0, 0, min(alpha, 160)),
                )
        else:
            # Center vignette band (text in middle)
            band_top = max(0, box_top - 60)
            band_bottom = min(h, box_bottom + 60)
            band_center = (band_top + band_bottom) / 2
            band_half = (band_bottom - band_top) / 2
            for i in range(band_top, band_bottom):
                dist = abs(i - band_center) / band_half
                alpha = int(140 * (1.0 - dist ** 1.2))
                grad_draw.line([(0, i), (w, i)], fill=(0, 0, 0, max(0, min(alpha, 140))))

        img = Image.alpha_composite(img, gradient)

    # Typography — use DeldedaOpen to match PPTX output
    FONT_SIZE   = 36
    LINE_HEIGHT = 50
    PAD_H       = 32
    PAD_BOTTOM  = 28

    try:
        font = ImageFont.truetype(str(_FONT_PATH), FONT_SIZE)
    except Exception:
        try:
            _POPPINS_BOLD = "/usr/share/fonts/truetype/google-fonts/Poppins-Bold.ttf"
            font = ImageFont.truetype(_POPPINS_BOLD, FONT_SIZE)
        except Exception:
            font = ImageFont.load_default()

    draw = ImageDraw.Draw(img)

    text_color = (255, 255, 255) if placement.get("text_color", "light") == "light" else (40, 28, 20)

    max_text_w = box_w - PAD_H * 2
    lines = _wrap_text(draw, text, font, max_text_w)

    total_text_h = len(lines) * LINE_HEIGHT

    y = box_bottom - PAD_BOTTOM - total_text_h
    y = max(y, box_top + 16)

    for line in lines:
        if y + FONT_SIZE > box_bottom:
            break
        if text_align == "center":
            try:
                line_w = draw.textlength(line, font=font)
            except AttributeError:
                bbox = draw.textbbox((0, 0), line, font=font)
                line_w = bbox[2] - bbox[0]
            x = box_left + (box_w - int(line_w)) // 2
        else:
            x = box_left + PAD_H
        stroke_fill = (0, 0, 0, 200) if text_color_key != "dark" else (255, 255, 255, 120)
        draw.text((x, y), line, font=font, fill=text_color,
                  stroke_width=5, stroke_fill=stroke_fill)
        y += LINE_HEIGHT

    result = img.convert("RGB")
    buf = io.BytesIO()
    result.save(buf, format="PNG", quality=92)
    return buf.getvalue()


def _wrap_text(draw: "ImageDraw.ImageDraw", text: str, font: "ImageFont.FreeTypeFont", max_w: int) -> list[str]:
    """Word-wrap using textlength for accurate measurement."""
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        try:
            line_w = draw.textlength(test, font=font)
        except AttributeError:
            bbox = draw.textbbox((0, 0), test, font=font)
            line_w = bbox[2] - bbox[0]
        if line_w <= max_w:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


# ── 3. Generate slide preview (async) ─────────────────────────────────────────

async def generate_slide_preview(draft_id: str, slide_index: int) -> bytes:
    """Load draft, analyze placement, render preview PNG, save placement to payload."""
    import asyncio

    draft = await get_draft(draft_id)
    if not draft:
        raise ValueError(f"Draft {draft_id} not found")

    slides = draft.payload.get("slides", [])
    if slide_index < 0 or slide_index >= len(slides):
        raise ValueError(f"Slide index {slide_index} out of range")

    text = slides[slide_index]
    if isinstance(text, list):
        text = "\n".join(str(item) for item in text)
    elif not isinstance(text, str):
        text = str(text)
    slide_images = list(draft.payload.get("slide_images", []))
    images = load_carousel_slide_images(draft_id, slide_images)

    img_bytes = images[slide_index] if slide_index < len(images) else None
    if not img_bytes:
        raise ValueError(f"No image for slide {slide_index}")

    # Get bias from correction history
    from bot.agents.carousel_export_agent import get_aggregate_bias
    role = SLIDE_ROLES[slide_index] if slide_index < len(SLIDE_ROLES) else "unknown"
    bias = get_aggregate_bias(role)

    loop = asyncio.get_running_loop()
    placement = await loop.run_in_executor(None, analyze_text_placement, img_bytes, slide_index, bias or None)

    # Save placement in payload
    payload = dict(draft.payload)
    placement_data = payload.get("placement_data", {})
    placement_data[str(slide_index)] = placement
    payload["placement_data"] = placement_data
    await update_draft(draft_id, payload=payload)

    # Render preview
    preview = await loop.run_in_executor(None, render_preview_png, img_bytes, text, placement)
    return preview


# ── 4. Generate all previews ──────────────────────────────────────────────────

async def generate_all_previews(draft_id: str) -> list[bytes]:
    """Generate preview PNGs for all slides."""
    from bot.services.drafts_store import get_draft

    draft = await get_draft(draft_id)
    if not draft:
        raise ValueError(f"Draft {draft_id} not found")

    slides = draft.payload.get("slides", [])
    results: list[bytes] = []
    for i in range(len(slides)):
        try:
            preview = await generate_slide_preview(draft_id, i)
            results.append(preview)
        except Exception as exc:
            logger.warning("Preview generation failed for slide %d: %s", i, exc)
    return results
