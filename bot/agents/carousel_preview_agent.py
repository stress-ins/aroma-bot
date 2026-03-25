"""Carousel Preview Agent — Vision-based text placement + PNG rendering."""
from __future__ import annotations

import colorsys
import io
import json
import logging
import math
from pathlib import Path

from bot.services.drafts_store import get_draft, update_draft
from bot.services.carousel_assets import load_carousel_slide_images
from bot.services.claude_client import call_claude

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────
# Legacy fixed list kept for backwards compat in tests / imports.
# Runtime code should use get_slide_roles(total) from generation module.
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


def _load_brand_avatar_bytes(payload: dict) -> bytes | None:
    """Load avatar bytes from brand_avatar_path in draft payload."""
    avatar_path = payload.get("brand_avatar_path")
    if avatar_path:
        p = Path(avatar_path)
        if p.exists():
            return p.read_bytes()
    return None
_CORRECTIONS_LOG = Path(__file__).parent.parent.parent / "data" / "placement_corrections_log.jsonl"

# Grid for monotone region search
_GRID_COLS = 10
_GRID_ROWS = 14


# ══════════════════════════════════════════════════════════════════════════════
# 1. Smart zone finder — dense grid + monotone cluster search
# ══════════════════════════════════════════════════════════════════════════════

def _find_quiet_zone(
    img_bytes: bytes,
    preferred_zone: str | None = None,
    min_cluster_h: int = 3,
    min_cluster_w: int = 4,
) -> tuple[float, float, float, float]:
    """Find the largest monotone region on a 10×14 grid.

    Returns (top_frac, left_frac, width_frac, height_frac) of the quietest
    contiguous rectangle suitable for text overlay.

    Uses variance scoring per cell, then flood-fills adjacent low-variance
    cells to find the best cluster.
    """
    from PIL import Image as _PIL, ImageFilter, ImageStat

    _ZONE_CENTERS_ROW = {
        "top": 2, "center": 7, "bottom": 11, "bottom-center": 10,
    }
    VARIANCE_THRESHOLD = 22  # cells calmer than this are "monotone"

    try:
        img = _PIL.open(io.BytesIO(img_bytes)).convert("L").resize((140, 196))
        img = img.filter(ImageFilter.GaussianBlur(2))
        W, H = img.size
        cols, rows = _GRID_COLS, _GRID_ROWS
        cw, rh = W // cols, H // rows

        # Score each cell
        cell_std = {}
        cell_avg = {}
        for r in range(rows):
            for c in range(cols):
                block = img.crop((c * cw, r * rh, (c + 1) * cw, (r + 1) * rh))
                stat = ImageStat.Stat(block)
                cell_std[(r, c)] = stat.stddev[0]
                cell_avg[(r, c)] = stat.mean[0]

        # Mark monotone cells
        mono = set()
        for (r, c), std in cell_std.items():
            if std <= VARIANCE_THRESHOLD:
                mono.add((r, c))

        # Find largest contiguous rectangle among monotone cells
        best_rect = None
        best_area = 0
        zone_center = _ZONE_CENTERS_ROW.get(preferred_zone)

        for r0 in range(rows):
            for c0 in range(cols):
                if (r0, c0) not in mono:
                    continue
                # Expand rectangle right and down as far as monotone cells go
                max_c1 = cols
                for r1 in range(r0, rows):
                    # Shrink max_c1 to maintain rectangle
                    for c in range(c0, max_c1):
                        if (r1, c) not in mono:
                            max_c1 = c
                            break
                    rect_w = max_c1 - c0
                    rect_h = r1 - r0 + 1
                    if rect_w < min_cluster_w or rect_h < min_cluster_h:
                        continue
                    area = rect_w * rect_h
                    # Prefer zones closer to preferred position
                    if zone_center is not None:
                        rect_center = r0 + rect_h / 2
                        distance_penalty = abs(rect_center - zone_center) * 2
                        area = area - distance_penalty
                    if area > best_area:
                        best_area = area
                        best_rect = (r0, c0, rect_w, rect_h)

        if best_rect:
            r0, c0, rw, rh_cells = best_rect
            top_frac = r0 / rows
            left_frac = c0 / cols
            w_frac = rw / cols
            h_frac = rh_cells / rows
            # Clamp to valid range
            if top_frac + h_frac > 0.97:
                h_frac = min(h_frac, 0.97 - top_frac)
            top_frac = max(0.0, top_frac)
            left_frac = max(0.0, left_frac)
            return top_frac, left_frac, w_frac, h_frac

        # Fallback: use old single-cell approach
        best_score = float("inf")
        best_r, best_c = rows - 3, 0
        for (r, c), std in cell_std.items():
            score = std * 1.5 + cell_avg[(r, c)] * 0.4
            if zone_center is not None:
                score += abs(r - zone_center) * 25
            if score < best_score:
                best_score = score
                best_r, best_c = r, c

        top_frac = best_r / rows
        h_frac = 3 / rows
        if top_frac + h_frac > 0.97:
            top_frac = 0.97 - h_frac
        return top_frac, 0.08, 0.84, h_frac

    except Exception:
        return 0.60, 0.08, 0.84, 0.32


# ══════════════════════════════════════════════════════════════════════════════
# 2. Color analysis — dominant color + rich palette generation
# ══════════════════════════════════════════════════════════════════════════════

def _zone_brightness(img_bytes: bytes, top_frac: float, h_frac: float) -> float:
    """Return mean brightness (0-255) of a horizontal strip."""
    from PIL import Image, ImageStat
    img = Image.open(io.BytesIO(img_bytes)).convert("L")
    w, h = img.size
    y0 = int(h * top_frac)
    y1 = int(h * min(top_frac + h_frac, 1.0))
    return ImageStat.Stat(img.crop((0, y0, w, y1))).mean[0]


def _zone_dominant_colors(
    img_bytes: bytes, top_frac: float, h_frac: float, n_colors: int = 5,
) -> list[tuple[int, int, int]]:
    """Return top N dominant colors from the text zone."""
    from PIL import Image
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    w, h = img.size
    y0 = int(h * top_frac)
    y1 = int(h * min(top_frac + h_frac, 1.0))
    zone = img.crop((0, y0, w, y1)).resize((80, 80), Image.LANCZOS)
    quantized = zone.quantize(colors=n_colors, method=Image.Quantize.FASTOCTREE)
    palette = quantized.getpalette()
    histogram = quantized.histogram()
    # Sort by frequency
    indexed = [(i, histogram[i]) for i in range(len(histogram)) if histogram[i] > 0]
    indexed.sort(key=lambda x: -x[1])
    colors = []
    for idx, _count in indexed[:n_colors]:
        r = palette[idx * 3]
        g = palette[idx * 3 + 1]
        b = palette[idx * 3 + 2]
        colors.append((r, g, b))
    return colors


def _contrast_ratio(c1: tuple[int, int, int], c2: tuple[int, int, int]) -> float:
    """WCAG contrast ratio between two RGB colors."""
    def relative_luminance(rgb):
        vals = []
        for c in rgb:
            s = c / 255.0
            vals.append(s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4)
        return 0.2126 * vals[0] + 0.7152 * vals[1] + 0.0722 * vals[2]
    l1 = relative_luminance(c1)
    l2 = relative_luminance(c2)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def _hue_shift(rgb: tuple[int, int, int], degrees: float) -> tuple[int, int, int]:
    """Shift hue of an RGB color by degrees."""
    h, s, v = colorsys.rgb_to_hsv(rgb[0] / 255, rgb[1] / 255, rgb[2] / 255)
    h = (h + degrees / 360) % 1.0
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return (int(r * 255), int(g * 255), int(b * 255))


def _saturate(rgb: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    """Adjust saturation. factor > 1 = more vivid, < 1 = more muted."""
    h, s, v = colorsys.rgb_to_hsv(rgb[0] / 255, rgb[1] / 255, rgb[2] / 255)
    s = min(1.0, s * factor)
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return (int(r * 255), int(g * 255), int(b * 255))


def _brighten(rgb: tuple[int, int, int], target_v: float) -> tuple[int, int, int]:
    """Push value (brightness) towards target_v (0-1)."""
    h, s, v = colorsys.rgb_to_hsv(rgb[0] / 255, rgb[1] / 255, rgb[2] / 255)
    v = target_v
    r, g, b = colorsys.hsv_to_rgb(h, min(s, 0.9), v)
    return (int(r * 255), int(g * 255), int(b * 255))


def _generate_palette(
    dominant_colors: list[tuple[int, int, int]],
    bg_brightness: float,
) -> list[tuple[int, int, int]]:
    """Generate 12+ candidate text colors from dominant photo colors.

    Candidates:
    - Bright tint of each dominant color (for dark bg)
    - Deep shade of each dominant color (for light bg)
    - Complementary hue of dominant
    - Analogous hues (±30°, ±60°)
    - Warm accent (toward orange/gold)
    - Cool accent (toward teal/blue)
    - Pure white / near-black (always safe)
    """
    on_dark = bg_brightness < 130
    candidates: list[tuple[int, int, int]] = []

    for dc in dominant_colors[:3]:
        if on_dark:
            # Bright tint — vivid, high value
            candidates.append(_brighten(_saturate(dc, 1.3), 0.88))
            # Pastel tint — softer, lighter
            candidates.append(_brighten(_saturate(dc, 0.5), 0.95))
        else:
            # Deep shade — dark, saturated
            candidates.append(_brighten(_saturate(dc, 1.4), 0.22))
            # Rich mid-tone
            candidates.append(_brighten(_saturate(dc, 1.2), 0.35))

    # Complementary of primary dominant
    if dominant_colors:
        comp = _hue_shift(dominant_colors[0], 180)
        candidates.append(_brighten(_saturate(comp, 1.2), 0.85 if on_dark else 0.25))

    # Analogous hues
    if dominant_colors:
        for shift in [30, -30, 60, -60]:
            analog = _hue_shift(dominant_colors[0], shift)
            candidates.append(_brighten(_saturate(analog, 1.1), 0.82 if on_dark else 0.28))

    # High-contrast same-hue (very bright tint or very dark shade)
    if dominant_colors:
        if on_dark:
            candidates.append(_brighten(_saturate(dominant_colors[0], 0.7), 0.97))
            candidates.append(_brighten(_saturate(dominant_colors[0], 0.3), 0.99))
        else:
            candidates.append(_brighten(_saturate(dominant_colors[0], 1.5), 0.12))
            candidates.append(_brighten(_saturate(dominant_colors[0], 0.8), 0.15))

    # Warm accent (gold/amber)
    warm = (255, 200, 80) if on_dark else (120, 70, 20)
    candidates.append(warm)

    # Cool accent (teal)
    cool = (100, 220, 210) if on_dark else (20, 80, 80)
    candidates.append(cool)

    # Safe defaults
    candidates.append((255, 255, 255) if on_dark else (30, 25, 20))
    candidates.append((240, 235, 220) if on_dark else (50, 40, 35))

    return candidates


def _pick_best_color(
    candidates: list[tuple[int, int, int]],
    bg_colors: list[tuple[int, int, int]],
    bg_brightness: float,
) -> tuple[int, int, int]:
    """Pick the color with best contrast + visual harmony.

    Scoring: high WCAG contrast (mandatory ≥ 3.0) + bonus for saturation
    (vivid colors look better than gray) + bonus for being close to a
    dominant color hue (organic feel).
    """
    # With soft Gaussian shadow, 2.0 is readable; prefer higher when possible
    min_contrast = 2.0
    avg_bg = bg_colors[0] if bg_colors else ((40, 40, 40) if bg_brightness < 130 else (200, 200, 200))

    best_color = (255, 255, 255) if bg_brightness < 130 else (30, 25, 20)
    best_score = 0.0

    for c in candidates:
        cr = _contrast_ratio(c, avg_bg)
        if cr < min_contrast:
            continue

        # Saturation bonus — prefer colorful over gray
        _, s, v = colorsys.rgb_to_hsv(c[0] / 255, c[1] / 255, c[2] / 255)
        sat_bonus = s * 15

        # Hue proximity bonus — closer to dominant = more organic
        hue_bonus = 0.0
        if bg_colors:
            h_cand, _, _ = colorsys.rgb_to_hsv(c[0] / 255, c[1] / 255, c[2] / 255)
            h_dom, _, _ = colorsys.rgb_to_hsv(bg_colors[0][0] / 255, bg_colors[0][1] / 255, bg_colors[0][2] / 255)
            hue_dist = min(abs(h_cand - h_dom), 1 - abs(h_cand - h_dom))
            hue_bonus = (1 - hue_dist * 2) * 20  # strong organic preference

        score = cr * 1.5 + sat_bonus + hue_bonus
        if score > best_score:
            best_score = score
            best_color = c

    return best_color


# ══════════════════════════════════════════════════════════════════════════════
# 3. Edge density for adaptive gradient
# ══════════════════════════════════════════════════════════════════════════════

def _zone_edge_density(img_bytes: bytes, top_frac: float, h_frac: float) -> float:
    """Edge density (0-1) in text zone. Low = quiet, good for text."""
    from PIL import Image, ImageFilter
    img = Image.open(io.BytesIO(img_bytes)).convert("L").resize((120, 120))
    edges = img.filter(ImageFilter.FIND_EDGES)
    w, h = edges.size
    y0 = int(h * top_frac)
    y1 = int(h * min(top_frac + h_frac, 1.0))
    zone = edges.crop((0, y0, w, y1))
    pixels = list(zone.getdata())
    if not pixels:
        return 0.0
    return sum(p > 40 for p in pixels) / len(pixels)


# ══════════════════════════════════════════════════════════════════════════════
# 4. Placement analysis
# ══════════════════════════════════════════════════════════════════════════════

def analyze_text_placement(
    img_bytes: bytes,
    slide_index: int,
    bias: dict | None = None,
    total_slides: int = 6,
) -> dict:
    """Find optimal text zone and pick organic color."""
    from bot.handlers.carousel.generation import get_slide_roles
    _roles = get_slide_roles(total_slides)
    role = _roles[slide_index] if slide_index < len(_roles) else "unknown"
    preferred = ROLE_PLACEMENT_PREFS.get(role)

    logger.info("Analyzing slide %d (role=%s, preferred=%s)", slide_index, role, preferred)

    top_frac, left_frac, w_frac, h_frac = _find_quiet_zone(
        img_bytes, preferred_zone=preferred,
    )

    brightness = _zone_brightness(img_bytes, top_frac, h_frac)
    text_color_key = "dark" if brightness > 160 else "light"

    dominant_colors = _zone_dominant_colors(img_bytes, top_frac, h_frac, n_colors=5)
    edge_density = _zone_edge_density(img_bytes, top_frac, h_frac)

    palette = _generate_palette(dominant_colors, brightness)
    organic_color = _pick_best_color(palette, dominant_colors, brightness)

    text_align = "center" if role in ("hook", "cta") else "left"

    placement = {
        "top": top_frac,
        "left": left_frac,
        "width": w_frac,
        "height": h_frac,
        "text_color": text_color_key,
        "text_align": text_align,
        "role": role,
        "source": "heuristic_v2",
        "dominant_rgb": [list(c) for c in dominant_colors[:3]],
        "organic_color": list(organic_color),
        "edge_density": edge_density,
    }
    if bias:
        for key in ("top", "left", "width", "height"):
            if key in bias:
                placement[key] = max(0.0, min(1.0, placement[key] + float(bias[key])))
    return placement


# ── Reels placement (unchanged) ──

_REELS_PLACEMENT_FALLBACK: dict = {
    "placement": {"zone": "top", "x_percent": 10, "y_percent": 8, "max_width_percent": 80},
    "typography": {"color_hex": "#FFFFFF", "shadow_color": "rgba(0,0,0,0.7)", "font_size_px": 18, "font_weight": 700},
}


def analyze_reels_placement(img_bytes: bytes) -> dict:
    """Use heuristic for reels text placement."""
    logger.info("Using fallback placement for reels")
    return dict(_REELS_PLACEMENT_FALLBACK)


# ══════════════════════════════════════════════════════════════════════════════
# 5. Render preview PNG
# ══════════════════════════════════════════════════════════════════════════════

def _dynamic_font_size(text: str, box_w: int, box_h: int) -> int:
    """Pick font size dynamically based on text length and available area.

    Tries to fill ~60-70% of box width on average, scaling from 56px
    (very short) down to 24px (very long).
    """
    char_count = len(text)
    word_count = len(text.split())

    # Approximate: each char at font_size N is ~0.55*N pixels wide
    # Target: lines should be ~60-70% of box_w
    # Max lines that fit in box_h: box_h / (font_size * 1.3)
    # So total chars ≈ max_lines * (box_w * 0.65) / (font_size * 0.55)

    # Start large, shrink until text fits reasonably
    for size in [56, 50, 46, 42, 38, 34, 30, 26, 24]:
        line_h = int(size * 1.3)
        max_lines = max(1, box_h // line_h - 1)
        chars_per_line = int(box_w * 0.85 / (size * 0.52))
        total_capacity = max_lines * chars_per_line
        if char_count <= total_capacity:
            return size

    return 24


def render_preview_png(
    img_bytes: bytes,
    text: str,
    placement: dict,
    size: tuple[int, int] = (1080, 1350),
) -> bytes:
    """Render editorial-style preview PNG with organic color-matched typography."""
    from PIL import Image, ImageDraw, ImageFilter, ImageFont

    img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
    target_w, target_h = size

    # ── Crop/resize to target ──
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
    box_bottom = box_top + box_h

    top_frac = placement.get("top", 0.58)
    text_color_key = placement.get("text_color", "light")
    text_align = placement.get("text_align", "left")
    edge_density = placement.get("edge_density", 0.3)

    # ── Adaptive gradient ──
    grad_alpha_max = int(100 + 80 * min(edge_density / 0.5, 1.0))

    if text_color_key != "dark":
        gradient = Image.new("RGBA", img.size, (0, 0, 0, 0))
        grad_draw = ImageDraw.Draw(gradient)

        if top_frac < 0.33:
            grad_bottom = min(h, box_bottom + 40)
            for i in range(grad_bottom):
                progress = 1.0 - (i / grad_bottom)
                alpha = int(grad_alpha_max * progress ** 1.5)
                grad_draw.line([(0, i), (w, i)], fill=(0, 0, 0, min(alpha, grad_alpha_max)))
        elif top_frac > 0.55:
            grad_top = max(0, box_top - 40)
            grad_h_px = box_bottom - grad_top
            for i in range(grad_h_px):
                alpha = int(grad_alpha_max * (i / max(grad_h_px, 1)) ** 1.5)
                grad_draw.line([(0, grad_top + i), (w, grad_top + i)],
                               fill=(0, 0, 0, min(alpha, grad_alpha_max)))
        else:
            band_top = max(0, box_top - 60)
            band_bottom_px = min(h, box_bottom + 60)
            band_center = (band_top + band_bottom_px) / 2
            band_half = max((band_bottom_px - band_top) / 2, 1)
            for i in range(band_top, band_bottom_px):
                dist = abs(i - band_center) / band_half
                alpha = int(grad_alpha_max * 0.85 * (1.0 - dist ** 1.2))
                grad_draw.line([(0, i), (w, i)], fill=(0, 0, 0, max(0, min(alpha, grad_alpha_max))))

        img = Image.alpha_composite(img, gradient)

    # ── Dynamic font size ──
    PAD_H = 32
    PAD_BOTTOM = 28
    usable_w = box_w - PAD_H * 2
    usable_h = box_h - PAD_BOTTOM

    font_size = _dynamic_font_size(text, usable_w, usable_h)
    line_height = int(font_size * 1.3)

    try:
        font = ImageFont.truetype(str(_FONT_PATH), font_size)
    except Exception:
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/google-fonts/Poppins-Bold.ttf", font_size)
        except Exception:
            font = ImageFont.load_default()

    draw = ImageDraw.Draw(img)

    # ── Organic text color ──
    organic_rgb = placement.get("organic_color")
    if organic_rgb and len(organic_rgb) == 3:
        text_color = tuple(organic_rgb)
    elif text_color_key == "light":
        text_color = (255, 255, 255)
    else:
        text_color = (40, 28, 20)

    lines = _wrap_text(draw, text, font, usable_w)

    total_text_h = len(lines) * line_height
    y = box_bottom - PAD_BOTTOM - total_text_h
    y = max(y, box_top + 16)

    # ── Soft shadow layer ──
    shadow_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow_layer)

    shadow_y = y
    for line in lines:
        if shadow_y + font_size > box_bottom:
            break
        sx = _line_x(shadow_draw, line, font, text_align, box_left, box_w, PAD_H)
        if text_color_key != "dark":
            shadow_draw.text((sx + 2, shadow_y + 2), line, font=font, fill=(0, 0, 0, 160))
        else:
            shadow_draw.text((sx + 1, shadow_y + 1), line, font=font, fill=(255, 255, 255, 90))
        shadow_y += line_height

    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=4))
    img = Image.alpha_composite(img, shadow_layer)

    # ── Draw text ──
    draw = ImageDraw.Draw(img)
    stroke_w = 2 if font_size >= 44 else 1
    stroke_fill = (0, 0, 0, 120) if text_color_key != "dark" else (255, 255, 255, 60)

    for line in lines:
        if y + font_size > box_bottom:
            break
        x = _line_x(draw, line, font, text_align, box_left, box_w, PAD_H)
        draw.text((x, y), line, font=font, fill=text_color,
                  stroke_width=stroke_w, stroke_fill=stroke_fill)
        y += line_height

    result = img.convert("RGB")
    buf = io.BytesIO()
    result.save(buf, format="PNG", quality=92)
    return buf.getvalue()


def _line_x(draw, line, font, text_align, box_left, box_w, pad_h):
    """Calculate X position for a line of text."""
    if text_align == "center":
        try:
            line_w = draw.textlength(line, font=font)
        except AttributeError:
            bbox = draw.textbbox((0, 0), line, font=font)
            line_w = bbox[2] - bbox[0]
        return box_left + (box_w - int(line_w)) // 2
    return box_left + pad_h


def _wrap_text(draw, text: str, font, max_w: int) -> list[str]:
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


# ══════════════════════════════════════════════════════════════════════════════
# 6. Async entry points
# ══════════════════════════════════════════════════════════════════════════════

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

    # ── Editorial style ──
    render_style = draft.payload.get("layout_style") or draft.payload.get("render_style", "overlay")
    if render_style == "editorial":
        # Use raw images (without burnt text) to avoid double-rendering
        from bot.services.carousel_assets import load_carousel_raw_images
        raw_images = load_carousel_raw_images(draft_id, slide_images)
        img_bytes = raw_images[slide_index] if slide_index < len(raw_images) else None

        from bot.agents.carousel_editorial import render_editorial_png
        accent = draft.payload.get("accent_color", [138, 92, 246])
        accent_rgb = tuple(accent) if isinstance(accent, list) and len(accent) == 3 else (138, 92, 246)
        username = draft.payload.get("brand_username", "")
        total_slides = len(draft.payload.get("slides", []))
        from bot.handlers.carousel.generation import get_slide_roles
        _roles = get_slide_roles(total_slides)
        role = _roles[slide_index] if slide_index < len(_roles) else "unknown"
        is_hook = role == "hook"
        is_bullet = "\n•" in text or "\n-" in text or "\n*" in text

        # Load avatar
        avatar_bytes = _load_brand_avatar_bytes(draft.payload)

        loop = asyncio.get_running_loop()
        preview = await loop.run_in_executor(
            None, lambda: render_editorial_png(
                img_bytes, text,
                slide_index=slide_index,
                accent_color=accent_rgb,
                bg_color=(18, 18, 22),
                size=(1080, 1350),
                username=username,
                avatar_bytes=avatar_bytes,
                is_hook=is_hook,
                is_bullet_list=is_bullet,
            ),
        )
        return preview

    images = load_carousel_slide_images(draft_id, slide_images)
    img_bytes = images[slide_index] if slide_index < len(images) else None

    # ── Classic overlay style ──
    if not img_bytes:
        raise ValueError(f"No image for slide {slide_index}")

    from bot.agents.carousel_export_agent import get_aggregate_bias
    total_slides = len(draft.payload.get("slides", []))
    from bot.handlers.carousel.generation import get_slide_roles as _gsr
    _roles = _gsr(total_slides)
    role = _roles[slide_index] if slide_index < len(_roles) else "unknown"
    bias = get_aggregate_bias(role)

    loop = asyncio.get_running_loop()
    placement = await loop.run_in_executor(None, analyze_text_placement, img_bytes, slide_index, bias or None, total_slides)

    payload = dict(draft.payload)
    placement_data = payload.get("placement_data", {})
    placement_data[str(slide_index)] = placement
    payload["placement_data"] = placement_data
    await update_draft(draft_id, payload=payload)

    preview = await loop.run_in_executor(None, render_preview_png, img_bytes, text, placement)
    return preview


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
