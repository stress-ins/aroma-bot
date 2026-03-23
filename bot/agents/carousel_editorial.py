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


def _parse_highlighted_text(text: str) -> list[tuple[str, bool]]:
    """Parse text into segments: (text, is_highlighted).

    Highlights come from:
    1. Explicit **bold** markdown markers
    2. Auto-detected key phrases (numbers, ALL CAPS, quotes)
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

    # Step 2: Auto-highlight in non-bold segments
    for seg_text, is_bold in raw_segments:
        if is_bold:
            segments.append((seg_text, True))
            continue

        # Find all auto-highlight spans
        highlights: list[tuple[int, int]] = []
        for pat in _HIGHLIGHT_PATTERNS:
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
        try:
            ww = draw.textlength(word + " ", font=font)
        except AttributeError:
            bbox = draw.textbbox((0, 0), word + " ", font=font)
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

    # ── Place photo at top ──
    if img_bytes:
        photo = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        # Cover crop to width × photo_h
        pr = photo.width / photo.height
        tr = w / photo_h
        if pr > tr:
            new_h = photo_h
            new_w = int(photo.width * photo_h / photo.height)
        else:
            new_w = w
            new_h = int(photo.height * w / photo.width)
        photo = photo.resize((new_w, new_h), Image.LANCZOS)
        lc = (new_w - w) // 2
        tc = (new_h - photo_h) // 2
        photo = photo.crop((lc, tc, lc + w, tc + photo_h))
        canvas.paste(photo, (0, 0))

        # Soft gradient transition from photo to bg
        gradient = Image.new("RGBA", (w, 60), (0, 0, 0, 0))
        gd = ImageDraw.Draw(gradient)
        for i in range(60):
            alpha = int(255 * (i / 60) ** 1.5)
            gd.line([(0, i), (w, i)], fill=(*bg_color, alpha))
        canvas.paste(Image.composite(
            Image.new("RGB", (w, 60), bg_color),
            canvas.crop((0, photo_h - 60, w, photo_h)),
            gradient.split()[3],
        ), (0, photo_h - 60))

    # ── Avatar + username bar ──
    bar_y = photo_h + 12 if img_bytes else 40
    PAD = 48

    if username:
        # Avatar circle
        avatar_size = 36
        ax = PAD
        ay = bar_y

        if avatar_bytes:
            try:
                av = Image.open(io.BytesIO(avatar_bytes)).convert("RGB")
                av = av.resize((avatar_size, avatar_size), Image.LANCZOS)
                # Circular mask
                mask = Image.new("L", (avatar_size, avatar_size), 0)
                md = ImageDraw.Draw(mask)
                md.ellipse((0, 0, avatar_size, avatar_size), fill=255)
                canvas.paste(av, (ax, ay), mask)
            except Exception:
                # Draw placeholder circle
                draw.ellipse((ax, ay, ax + avatar_size, ay + avatar_size),
                             fill=(60, 60, 70))

            # Username text
            ufont = _load_font(18)
            ux = ax + avatar_size + 10
            # Dash line
            draw.line([(ux, ay + avatar_size // 2), (ux + 20, ay + avatar_size // 2)],
                      fill=(100, 100, 110), width=2)
            draw.text((ux + 26, ay + 8), username, font=ufont, fill=(200, 200, 210))
        else:
            ufont = _load_font(18)
            draw.text((ax, ay + 8), username, font=ufont, fill=(200, 200, 210))

        bar_y += avatar_size + 20

    # ── Parse and render text ──
    segments = _parse_highlighted_text(text)

    # Determine font size based on text length
    char_count = len(text)
    if is_bullet_list:
        title_size = 38
        body_size = 26
    elif char_count <= 40:
        title_size = 52
        body_size = 52
    elif char_count <= 80:
        title_size = 46
        body_size = 46
    elif char_count <= 150:
        title_size = 38
        body_size = 30
    else:
        title_size = 34
        body_size = 26

    usable_w = w - PAD * 2
    text_y = bar_y

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

        # Draw title in accent
        if title:
            title_font = _load_font(title_size)
            title_segs = _parse_highlighted_text(title)
            title_lines = _wrap_rich_text(draw, title_segs, title_font, usable_w)
            line_h = int(title_size * 1.35)
            for tl in title_lines:
                _draw_rich_line(draw, tl, PAD, text_y, title_font,
                                (255, 255, 255), accent_color, "left", PAD, usable_w)
                text_y += line_h
            text_y += 12

        # Draw bullets
        if bullets:
            bullet_font = _load_font(body_size)
            line_h = int(body_size * 1.5)
            for bullet in bullets:
                b_segs = _parse_highlighted_text(bullet)
                b_lines = _wrap_rich_text(draw, b_segs, bullet_font, usable_w - 30)
                # Bullet dot
                dot_y = text_y + body_size // 3
                draw.ellipse((PAD, dot_y, PAD + 8, dot_y + 8), fill=(180, 180, 190))
                for j, bl in enumerate(b_lines):
                    _draw_rich_line(draw, bl, PAD + 26, text_y, bullet_font,
                                    (220, 220, 230), accent_color, "left", PAD + 26, usable_w - 26)
                    text_y += line_h
                text_y += 4
    else:
        # Regular text — all same size, center-aligned
        font = _load_font(title_size)
        text_lines = _wrap_rich_text(draw, segments, font, usable_w)
        line_h = int(title_size * 1.35)

        for tl in text_lines:
            if text_y + title_size > h - 60:
                break
            _draw_rich_line(draw, tl, PAD, text_y, font,
                            (255, 255, 255), accent_color, "center", PAD, usable_w)
            text_y += line_h

    # ── "Свайпай →" on hook slide ──
    if is_hook:
        swipe_font = _load_font(16)
        swipe_text = "СВАЙПАЙ  →"
        try:
            sw = draw.textlength(swipe_text, font=swipe_font)
        except AttributeError:
            sw = 100
        sx = (w - int(sw)) // 2
        sy = h - 50
        draw.text((sx, sy), swipe_text, font=swipe_font, fill=(140, 140, 150))

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
