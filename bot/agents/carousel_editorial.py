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
) -> bytes:
    """Render editorial-style slide: photo top, solid bg + highlighted text bottom."""
    from PIL import Image, ImageDraw, ImageFilter

    w, h = size

    # Photo takes top 55%, text area bottom 45%
    photo_h = int(h * 0.55) if img_bytes else 0
    text_area_h = h - photo_h

    canvas = Image.new("RGB", (w, h), bg_color)
    draw = ImageDraw.Draw(canvas)

    # ── Place photo at top (fit-width — full width, no cropping) ──
    if img_bytes:
        photo = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        # Scale to full width, keep aspect ratio (may exceed photo_h)
        scale = w / photo.width
        new_w = w
        new_h = int(photo.height * scale)
        photo = photo.resize((new_w, new_h), Image.LANCZOS)
        # If taller than photo_h, crop from center vertically
        if new_h > photo_h:
            crop_top = (new_h - photo_h) // 2
            photo = photo.crop((0, crop_top, new_w, crop_top + photo_h))
            new_h = photo_h
        # Center vertically in photo area
        paste_y = (photo_h - new_h) // 2
        canvas.paste(photo, (0, paste_y))

        # Soft gradient transition from photo to bg (longer for smoother blend)
        gradient_h = int(120 * h / 1350)
        gradient = Image.new("RGBA", (w, gradient_h), (0, 0, 0, 0))
        gd = ImageDraw.Draw(gradient)
        for i in range(gradient_h):
            alpha = int(255 * (i / gradient_h) ** 1.5)
            gd.line([(0, i), (w, i)], fill=(*bg_color, alpha))
        canvas.paste(Image.composite(
            Image.new("RGB", (w, gradient_h), bg_color),
            canvas.crop((0, photo_h - gradient_h, w, photo_h)),
            gradient.split()[3],
        ), (0, photo_h - gradient_h))

    PAD = 48

    # ── Zigzag divider between photo and text area ──
    if img_bytes:
        divider_y = photo_h + 4
        tooth_w = 18  # width of each triangle tooth
        tooth_h = 8   # height of tooth peak
        divider_color = (200, 200, 210)
        x = PAD
        while x < w - PAD:
            peak_x = x + tooth_w // 2
            end_x = min(x + tooth_w, w - PAD)
            # Draw rounded triangle: up-peak
            draw.polygon(
                [(x, divider_y + tooth_h), (peak_x, divider_y), (end_x, divider_y + tooth_h)],
                fill=divider_color,
            )
            # Round the peak with a small ellipse
            r = 3
            draw.ellipse(
                (peak_x - r, divider_y - r, peak_x + r, divider_y + r),
                fill=divider_color,
            )
            x += tooth_w

    # ── Avatar + username bar (centered) ──
    bar_y = photo_h + 18 if img_bytes else 40

    if username:
        avatar_size = 48
        ufont = _load_font(22)
        dash_w = 28
        gap_avatar_dash = 14
        gap_dash_text = 6

        # Measure username width for centering
        try:
            uname_w = int(draw.textlength(username, font=ufont))
        except AttributeError:
            bbox = draw.textbbox((0, 0), username, font=ufont)
            uname_w = bbox[2] - bbox[0]

        total_bar_w = avatar_size + gap_avatar_dash + dash_w + gap_dash_text + uname_w
        ax = (w - total_bar_w) // 2
        ay = bar_y

        if avatar_bytes:
            try:
                av = Image.open(io.BytesIO(avatar_bytes)).convert("RGB")
                av = av.resize((avatar_size, avatar_size), Image.LANCZOS)
                mask = Image.new("L", (avatar_size, avatar_size), 0)
                md = ImageDraw.Draw(mask)
                md.ellipse((0, 0, avatar_size, avatar_size), fill=255)
                canvas.paste(av, (ax, ay), mask)
            except Exception:
                # Fallback: colored circle with first letter
                draw.ellipse((ax, ay, ax + avatar_size, ay + avatar_size),
                             fill=tuple(accent_color))
                letter = username[0].upper()
                lf = _load_font(26)
                try:
                    lw = int(draw.textlength(letter, font=lf))
                except AttributeError:
                    lw = 16
                draw.text((ax + (avatar_size - lw) // 2, ay + 8), letter,
                          font=lf, fill=(255, 255, 255))
        else:
            # No avatar photo — draw accent-colored circle with first letter
            draw.ellipse((ax, ay, ax + avatar_size, ay + avatar_size),
                         fill=tuple(accent_color))
            letter = username[0].upper()
            lf = _load_font(26)
            try:
                lw = int(draw.textlength(letter, font=lf))
            except AttributeError:
                lw = 16
            draw.text((ax + (avatar_size - lw) // 2, ay + 8), letter,
                      font=lf, fill=(255, 255, 255))

        # Dash line between avatar and username (like reference)
        ux = ax + avatar_size + gap_avatar_dash
        dash_y = ay + avatar_size // 2
        draw.line([(ux, dash_y), (ux + dash_w, dash_y)],
                  fill=(180, 180, 190), width=2)
        draw.text((ux + dash_w + gap_dash_text, ay + 12), username,
                  font=ufont, fill=(220, 220, 230))

        bar_y += avatar_size + 24

    # ── Parse and render text ──
    # Uppercase transformation for headlines (not bullet body)
    uppercased = not is_bullet_list
    display_text = text.upper() if uppercased else text
    segments = _parse_highlighted_text(display_text, skip_caps_highlight=uppercased)

    # Determine font size based on text length
    char_count = len(text)
    if is_bullet_list:
        title_size = 52
        body_size = 36
    elif char_count <= 40:
        title_size = 80
        body_size = 80
    elif char_count <= 80:
        title_size = 68
        body_size = 68
    elif char_count <= 150:
        title_size = 56
        body_size = 42
    else:
        title_size = 48
        body_size = 34

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

    # ── "Свайпай →" on hook slide ──
    if is_hook:
        swipe_font = _load_font(28)
        swipe_text = "СВАЙПАЙ  >>"
        try:
            sw = draw.textlength(swipe_text, font=swipe_font)
        except AttributeError:
            sw = 160
        sx = (w - int(sw)) // 2
        sy = h - 60
        swipe_color = (
            min(255, accent_color[0] // 2 + 70),
            min(255, accent_color[1] // 2 + 70),
            min(255, accent_color[2] // 2 + 70),
        )
        draw.text((sx, sy), swipe_text, font=swipe_font, fill=swipe_color)

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
