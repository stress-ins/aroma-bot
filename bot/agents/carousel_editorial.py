"""Editorial carousel renderer — solid-background text slides with accent highlights.

Layout: photo occupies top ~55%, solid dark background bottom ~45%.
Text is rendered with auto-highlighted key phrases in accent color.
Avatar + username from brand settings. "Свайпай →" on hook slides.
"""
from __future__ import annotations

import io
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

_FONT_PATH = Path(__file__).parent.parent.parent / "assets" / "fonts" / "DeldedaOpen.ttf"

# Words/patterns that should auto-highlight when not wrapped in **bold**
_HIGHLIGHT_PATTERNS = [
    # Numbers with units (e.g. "170 км", "$500 млрд", "18 000", "9 млн")
    re.compile(r"\b\d[\d\s,.]*\s*(?:км|м|млн|млрд|тыс|%|шт|чел(?:овек)?|руб|долл|\$|€|₽)\b", re.IGNORECASE),
    # Standalone big numbers
    re.compile(r"\b\d[\d\s,.]{2,}\b"),
    # ALL CAPS words (3+ letters, Cyrillic or Latin)
    re.compile(r"\b[A-ZА-ЯЁ]{3,}\b"),
    # Quoted phrases «...» or "..."
    re.compile(r"[«\"][^»\"]+[»\"]"),
]


def _parse_highlighted_text(text: str, *, skip_caps_highlight: bool = False) -> list[tuple[str, bool]]:
    """Parse text into segments: (text, is_highlighted).

    Highlights come from:
    1. Explicit **bold** markdown markers
    2. Auto-detected key phrases (numbers, ALL CAPS, quotes)

    When skip_caps_highlight=True, the ALL CAPS pattern is skipped
    (useful when the entire text has been uppercased).
    """
    # Step 1: Extract explicit **bold** markers
    segments: list[tuple[str, bool]] = []
    parts = re.split(r"(\*\*[^*]+\*\*)", text)

    raw_segments: list[tuple[str, bool]] = []
    for part in parts:
        if part.startswith("**") and part.endswith("**"):
            raw_segments.append((part[2:-2], True))
        else:
            raw_segments.append((part, False))

    # Choose which patterns to apply
    patterns = [p for i, p in enumerate(_HIGHLIGHT_PATTERNS) if not (skip_caps_highlight and i == 2)]

    # Step 2: Auto-highlight in non-bold segments
    for seg_text, is_bold in raw_segments:
        if is_bold:
            segments.append((seg_text, True))
            continue

        # Find all auto-highlight spans
        highlights: list[tuple[int, int]] = []
        for pat in patterns:
            for m in pat.finditer(seg_text):
                highlights.append((m.start(), m.end()))

        if not highlights:
            segments.append((seg_text, False))
            continue

        # Merge overlapping spans
        highlights.sort()
        merged: list[tuple[int, int]] = [highlights[0]]
        for s, e in highlights[1:]:
            if s <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], e))
            else:
                merged.append((s, e))

        # Split text by highlight spans
        pos = 0
        for s, e in merged:
            if pos < s:
                segments.append((seg_text[pos:s], False))
            segments.append((seg_text[s:e], True))
            pos = e
        if pos < len(seg_text):
            segments.append((seg_text[pos:], False))

    return [(t, h) for t, h in segments if t]


def _load_font(size: int):
    """Load font with fallbacks."""
    from PIL import ImageFont
    try:
        return ImageFont.truetype(str(_FONT_PATH), size)
    except Exception:
        try:
            return ImageFont.truetype("/usr/share/fonts/truetype/google-fonts/Poppins-Bold.ttf", size)
        except Exception:
            return ImageFont.load_default()


def _wrap_rich_text(
    draw, segments: list[tuple[str, bool]], font, max_w: int,
) -> list[list[tuple[str, bool]]]:
    """Word-wrap highlighted text into lines, preserving highlight info."""
    # Flatten to words with highlight flag
    words: list[tuple[str, bool]] = []
    for text, hl in segments:
        for word in text.split():
            words.append((word, hl))

    lines: list[list[tuple[str, bool]]] = []
    current_line: list[tuple[str, bool]] = []
    current_text = ""

    for word, hl in words:
        test = f"{current_text} {word}".strip()
        try:
            line_w = draw.textlength(test, font=font)
        except AttributeError:
            bbox = draw.textbbox((0, 0), test, font=font)
            line_w = bbox[2] - bbox[0]
        if line_w <= max_w:
            current_text = test
            current_line.append((word, hl))
        else:
            if current_line:
                lines.append(current_line)
            current_line = [(word, hl)]
            current_text = word

    if current_line:
        lines.append(current_line)
    return lines


def _draw_rich_line(
    draw, line_words: list[tuple[str, bool]], x: int, y: int,
    font, base_color: tuple, accent_color: tuple, align: str,
    box_left: int, box_w: int,
):
    """Draw a line with mixed base/accent colored words."""
    full_text = " ".join(w for w, _ in line_words)
    try:
        total_w = draw.textlength(full_text, font=font)
    except AttributeError:
        bbox = draw.textbbox((0, 0), full_text, font=font)
        total_w = bbox[2] - bbox[0]

    if align == "center":
        cx = box_left + (box_w - int(total_w)) // 2
    else:
        cx = x

    for i, (word, hl) in enumerate(line_words):
        color = accent_color if hl else base_color
        draw.text((cx, y), word, font=font, fill=color)
        # Don't add space before punctuation in the next word
        next_is_punct = (i + 1 < len(line_words) and
                         line_words[i + 1][0][:1] in ",.;:!?—–")
        spacer = "" if next_is_punct else " "
        try:
            ww = draw.textlength(word + spacer, font=font)
        except AttributeError:
            bbox = draw.textbbox((0, 0), word + spacer, font=font)
            ww = bbox[2] - bbox[0]
        cx += int(ww)


_DIVIDERS_DIR = Path(__file__).parent.parent.parent / "assets" / "carousel_dividers"
_SWIPE_ARROW_PATH = Path(__file__).parent.parent.parent / "assets" / "carousel_swipe" / "swipe_arrow.png"

DIVIDER_STYLES = [
    "divider_01_pike_thick", "divider_02_pike_thin", "divider_03_wave",
    "divider_04_wave_sharp", "divider_05_bold", "divider_06_arrow_line",
    "divider_07_medium", "divider_08_tall", "divider_09_round",
    "divider_10_rounder", "divider_11_line_dots", "divider_12_asymm",
]
DEFAULT_DIVIDER = "divider_06_arrow_line"


def _load_divider_png(style: str = DEFAULT_DIVIDER):
    """Load a divider PNG template (RGBA with transparent center gap)."""
    from PIL import Image
    path = _DIVIDERS_DIR / f"{style}.png"
    if not path.exists():
        path = _DIVIDERS_DIR / f"{DEFAULT_DIVIDER}.png"
    if not path.exists():
        return None
    return Image.open(path).convert("RGBA")


def _load_swipe_arrow():
    """Load swipe arrow PNG (black on white/transparent)."""
    from PIL import Image
    if not _SWIPE_ARROW_PATH.exists():
        return None
    return Image.open(_SWIPE_ARROW_PATH).convert("RGBA")


def _draw_avatar_placeholder(draw, x, y, diameter, username, accent_color):
    """Draw accent-colored circle with first letter of username."""
    draw.ellipse((x, y, x + diameter, y + diameter), fill=tuple(accent_color))
    letter = username[0].upper() if username else "?"
    lf = _load_font(max(12, diameter * 2 // 3))
    try:
        lw = int(draw.textlength(letter, font=lf))
    except AttributeError:
        lw = diameter // 2
    lh = max(12, diameter * 2 // 3)
    draw.text((x + (diameter - lw) // 2, y + (diameter - lh) // 2),
              letter, font=lf, fill=(255, 255, 255))


def render_editorial_png(
    img_bytes: bytes | None,
    text: str,
    slide_index: int = 0,
    accent_color: tuple[int, int, int] = (138, 92, 246),  # purple default
    bg_color: tuple[int, int, int] = (18, 18, 22),
    size: tuple[int, int] = (1080, 1350),
    username: str = "",
    avatar_bytes: bytes | None = None,
    is_hook: bool = False,
    is_bullet_list: bool = False,
    divider_style: str = DEFAULT_DIVIDER,
) -> bytes:
    """Render editorial-style slide: photo top, solid bg + highlighted text bottom."""
    from PIL import Image, ImageDraw, ImageFilter

    w, h = size

    # Layer 1: photo (top ~50%), Layer 2: dark rect (bottom ~50%), Layer 3: gradient
    dark_rect_top = int(h * 0.50)
    photo_h = dark_rect_top if img_bytes else 0

    canvas = Image.new("RGB", (w, h), bg_color)
    draw = ImageDraw.Draw(canvas)

    # ── Layer 1: Photo — fit-width, crop to photo zone ──
    if img_bytes:
        photo = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        scale = w / photo.width
        new_w = w
        new_h = int(photo.height * scale)
        photo = photo.resize((new_w, new_h), Image.LANCZOS)
        if new_h > photo_h:
            # Crop from top (show upper part of photo, more natural)
            photo = photo.crop((0, 0, new_w, photo_h))
        canvas.paste(photo, (0, 0))

    # ── Layer 2: Dark rect — bottom 50% ──
    draw.rectangle([(0, dark_rect_top), (w, h)], fill=bg_color)

    # ── Layer 3: Gradient overlay — smooth transition (80px) ──
    if img_bytes:
        gradient_h = 80
        gradient = Image.new("RGBA", (w, gradient_h), (0, 0, 0, 0))
        gd = ImageDraw.Draw(gradient)
        for i in range(gradient_h):
            alpha = int(255 * (i / gradient_h) ** 1.5)
            gd.line([(0, i), (w, i)], fill=(*bg_color, alpha))
        canvas.paste(Image.composite(
            Image.new("RGB", (w, gradient_h), bg_color),
            canvas.crop((0, dark_rect_top - gradient_h, w, dark_rect_top)),
            gradient.split()[3],
        ), (0, dark_rect_top - gradient_h))

    PAD = 48

    # ── Author Divider: PNG template + avatar + username ──
    bar_y = photo_h + 18 if img_bytes else 40

    if username:
        AVATAR_D = 40
        FONT_SIZE = 13
        ufont = _load_font(FONT_SIZE)

        try:
            uname_w = int(draw.textlength(username, font=ufont))
        except AttributeError:
            bbox = draw.textbbox((0, 0), username, font=ufont)
            uname_w = bbox[2] - bbox[0]

        divider_img = _load_divider_png(divider_style)
        if divider_img:
            # Scale divider to ~60% of slide width, keep aspect ratio
            target_div_w = int(w * 0.60)
            div_scale = target_div_w / divider_img.width
            div_w = target_div_w
            div_h = int(divider_img.height * div_scale)
            divider_img = divider_img.resize((div_w, div_h), Image.LANCZOS)

            # Center divider horizontally
            div_x = (w - div_w) // 2
            div_y = bar_y
            canvas.paste(divider_img, (div_x, div_y), divider_img)

            # Avatar in center of divider gap
            center_y = div_y + div_h // 2
            av_x = (w - AVATAR_D) // 2
            av_y = center_y - AVATAR_D // 2
            if avatar_bytes:
                try:
                    av = Image.open(io.BytesIO(avatar_bytes)).convert("RGB")
                    av = av.resize((AVATAR_D, AVATAR_D), Image.LANCZOS)
                    mask = Image.new("L", (AVATAR_D, AVATAR_D), 0)
                    ImageDraw.Draw(mask).ellipse((0, 0, AVATAR_D, AVATAR_D), fill=255)
                    canvas.paste(av, (av_x, av_y), mask)
                except Exception:
                    _draw_avatar_placeholder(draw, av_x, av_y, AVATAR_D, username, accent_color)
            else:
                _draw_avatar_placeholder(draw, av_x, av_y, AVATAR_D, username, accent_color)

            # Username below divider
            name_x = (w - uname_w) // 2
            name_y = div_y + div_h + 4
            draw.text((name_x, name_y), username, font=ufont, fill=(255, 255, 255))

            bar_y = name_y + FONT_SIZE + 12
        else:
            # Fallback: just username centered
            name_x = (w - uname_w) // 2
            draw.text((name_x, bar_y), username, font=ufont, fill=(255, 255, 255))
            bar_y += FONT_SIZE + 20

    # ── Parse and render text ──
    # Uppercase transformation for headlines (not bullet body)
    uppercased = not is_bullet_list
    display_text = text.upper() if uppercased else text
    segments = _parse_highlighted_text(display_text, skip_caps_highlight=uppercased)

    # Determine font size — minimum 48pt for titles per spec
    char_count = len(text)
    if is_bullet_list:
        title_size = 56
        body_size = 40
    elif char_count <= 40:
        title_size = 80
        body_size = 80
    elif char_count <= 80:
        title_size = 68
        body_size = 68
    elif char_count <= 150:
        title_size = 56
        body_size = 48
    else:
        title_size = 52
        body_size = 40

    # Tighter line height for large fonts (magazine style)
    line_mult = 1.25 if title_size >= 60 else 1.35

    usable_w = w - PAD * 2
    swipe_reserve = 70 if is_hook else 30

    if is_bullet_list:
        # Split into title (first line before •) and bullets
        lines_raw = text.split("\n")
        title = ""
        bullets = []
        for line in lines_raw:
            stripped = line.strip()
            if stripped.startswith("•") or stripped.startswith("-") or stripped.startswith("*"):
                bullets.append(stripped.lstrip("•-* ").strip())
            elif not bullets and not title:
                title = stripped
            elif not bullets:
                title += " " + stripped
            else:
                bullets.append(stripped)

        # Pre-calculate total height for vertical centering
        title_font = _load_font(title_size) if title else None
        title_upper = title.upper()
        title_segs = _parse_highlighted_text(title_upper, skip_caps_highlight=True) if title else []
        title_lines = _wrap_rich_text(draw, title_segs, title_font, usable_w) if title_segs else []
        title_line_h = int(title_size * 1.35)
        total_title_h = len(title_lines) * title_line_h + (12 if title else 0)

        bullet_font = _load_font(body_size) if bullets else None
        bullet_line_h = int(body_size * 1.5)
        total_bullets_h = 0
        bullet_wrapped = []
        for bullet in bullets:
            b_segs = _parse_highlighted_text(bullet)
            b_lines = _wrap_rich_text(draw, b_segs, bullet_font, usable_w - 30)
            bullet_wrapped.append(b_lines)
            total_bullets_h += len(b_lines) * bullet_line_h + 4

        total_text_h = total_title_h + total_bullets_h
        available_h = (h - swipe_reserve) - bar_y
        text_y = bar_y + max(0, (available_h - total_text_h) // 2)

        # Draw title in accent
        if title_lines:
            for tl in title_lines:
                _draw_rich_line(draw, tl, PAD, text_y, title_font,
                                (255, 255, 255), accent_color, "left", PAD, usable_w)
                text_y += title_line_h
            text_y += 12

        # Draw bullets
        for b_lines in bullet_wrapped:
            dot_y = text_y + body_size // 3
            draw.ellipse((PAD, dot_y, PAD + 8, dot_y + 8), fill=(180, 180, 190))
            for bl in b_lines:
                _draw_rich_line(draw, bl, PAD + 26, text_y, bullet_font,
                                (220, 220, 230), accent_color, "left", PAD + 26, usable_w - 26)
                text_y += bullet_line_h
            text_y += 4
    else:
        # Regular text — uppercase, center-aligned, vertically centered
        font = _load_font(title_size)
        text_lines = _wrap_rich_text(draw, segments, font, usable_w)
        line_h = int(title_size * line_mult)
        total_text_h = len(text_lines) * line_h

        available_h = (h - swipe_reserve) - bar_y
        text_y = bar_y + max(0, (available_h - total_text_h) // 2)

        for tl in text_lines:
            if text_y + title_size > h - swipe_reserve:
                break
            _draw_rich_line(draw, tl, PAD, text_y, font,
                            (255, 255, 255), accent_color, "center", PAD, usable_w)
            text_y += line_h

    # ── Swipe CTA: PNG arrow image ──
    if is_hook:
        from PIL import ImageOps
        arrow_img = _load_swipe_arrow()
        if arrow_img:
            # Invert black arrow to white for dark background
            r, g, b, a = arrow_img.split()
            rgb = Image.merge("RGB", (r, g, b))
            rgb = ImageOps.invert(rgb)
            arrow_img = Image.merge("RGBA", (*rgb.split(), a))

            # Scale arrow to ~120px wide
            arrow_target_w = 120
            ar_scale = arrow_target_w / arrow_img.width
            ar_w = arrow_target_w
            ar_h = int(arrow_img.height * ar_scale)
            arrow_img = arrow_img.resize((ar_w, ar_h), Image.LANCZOS)

            ar_x = (w - ar_w) // 2
            ar_y = h - 28 - ar_h
            canvas.paste(arrow_img, (ar_x, ar_y), arrow_img)
        else:
            # Fallback: text-only CTA
            cta_font = _load_font(14)
            cta_text = "СВАЙПАЙ  >>"
            try:
                cta_tw = int(draw.textlength(cta_text, font=cta_font))
            except AttributeError:
                cta_tw = 100
            draw.text(((w - cta_tw) // 2, h - 42), cta_text,
                      font=cta_font, fill=(255, 255, 255))

    buf = io.BytesIO()
    canvas.save(buf, format="PNG", quality=92)
    return buf.getvalue()


# ── Image prompt modifier for editorial style ──

def editorial_image_prompt_modifier(base_prompt: str) -> str:
    """Modify image generation prompt for editorial layout.

    The photo only occupies the top ~55% of the slide, so the prompt
    should focus on a subject in the upper/center part with clean
    composition that doesn't need bottom area.
    """
    additions = (
        "Top-heavy composition with the main subject in the upper half. "
        "Clean, uncluttered bottom edge that fades to dark. "
        "No text, no watermarks, no UI elements in the image."
    )
    return f"{base_prompt.rstrip('.')}. {additions}"
