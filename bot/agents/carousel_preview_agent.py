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

def analyze_text_placement(
    img_bytes: bytes,
    slide_index: int,
    bias: dict | None = None,
) -> dict:
    """Use Claude Vision to find optimal text zone on a slide image.

    Returns dict with keys: top, left, width, height, text_color, role, source.
    """
    from bot.handlers.carousel import _find_text_zone

    role = SLIDE_ROLES[slide_index] if slide_index < len(SLIDE_ROLES) else "unknown"
    pref = ROLE_PLACEMENT_PREFS.get(role, "center")

    try:
        b64 = base64.standard_b64encode(img_bytes).decode()
        prompt = (
            f"You are an image layout analyst for Instagram carousel slides.\n"
            f"Find the best \"quiet zone\" on this image where overlay text will be readable.\n"
            f"The slide role is \"{role}\", preferred placement: \"{pref}\".\n\n"
            f"Return ONLY a JSON object (no markdown) with these fields:\n"
            f"- \"top\": float 0.0-1.0 (vertical start as fraction of image height)\n"
            f"- \"left\": float 0.0-1.0 (horizontal start as fraction of image width)\n"
            f"- \"width\": float 0.0-1.0 (text box width as fraction)\n"
            f"- \"height\": float 0.0-1.0 (text box height as fraction)\n"
            f"- \"text_color\": \"light\" or \"dark\" (what text color works best)\n"
        )

        raw = call_claude(
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": b64,
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }],
            max_tokens=200,
            context="carousel_preview",
        )
        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()

        placement = json.loads(raw)

        # Validate required keys
        for key in ("top", "left", "width", "height", "text_color"):
            if key not in placement:
                raise ValueError(f"Missing key: {key}")

        # Clamp values
        for key in ("top", "left", "width", "height"):
            placement[key] = max(0.0, min(1.0, float(placement[key])))

        # Apply bias from correction history
        if bias:
            for key in ("top", "left", "width", "height"):
                if key in bias:
                    placement[key] = max(0.0, min(1.0, placement[key] + float(bias[key])))

        placement["role"] = role
        placement["source"] = "vision"
        return placement

    except Exception as exc:
        logger.warning("Vision placement failed (slide %d): %s — falling back to heuristic", slide_index, exc)
        top_frac, h_frac = _find_text_zone(img_bytes)
        return {
            "top": top_frac,
            "left": 0.08,
            "width": 0.84,
            "height": h_frac,
            "text_color": "light",
            "role": role,
            "source": "heuristic",
        }


# ── 2. Render preview PNG ─────────────────────────────────────────────────────

def render_preview_png(
    img_bytes: bytes,
    text: str,
    placement: dict,
    size: tuple[int, int] = (1080, 1350),
) -> bytes:
    """Render a preview PNG with text overlaid on the image."""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
    target_w, target_h = size

    # Crop-to-fill: scale to cover, then center-crop
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

    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    img = img.crop((left, top, left + target_w, top + target_h))

    w, h = size

    box_left = int(w * placement.get("left", 0.08))
    box_top = int(h * placement.get("top", 0.6))
    box_w = int(w * placement.get("width", 0.84))
    box_h = int(h * placement.get("height", 0.25))

    # Semi-transparent overlay: #180E08 at 58% opacity
    overlay = Image.new("RGBA", (box_w, box_h), (0x18, 0x0E, 0x08, int(255 * 0.58)))
    img.paste(overlay, (box_left, box_top), overlay)

    draw = ImageDraw.Draw(img)

    # Load font
    try:
        font = ImageFont.truetype(str(_FONT_PATH), 32)
    except Exception:
        font = ImageFont.load_default()

    text_color = (255, 255, 255) if placement.get("text_color", "light") == "light" else (61, 43, 31)

    # Word-wrap text
    margin = 24
    max_text_w = box_w - margin * 2
    lines = _wrap_text(draw, text, font, max_text_w)

    y = box_top + margin
    for line in lines:
        if y + 36 > box_top + box_h:
            break
        draw.text((box_left + margin, y), line, fill=text_color, font=font)
        y += 40

    # Convert to RGB for PNG output
    result = img.convert("RGB")
    buf = io.BytesIO()
    result.save(buf, format="PNG")
    return buf.getvalue()


def _wrap_text(draw: "ImageDraw.ImageDraw", text: str, font: "ImageFont.FreeTypeFont", max_w: int) -> list[str]:
    """Simple word-wrap."""
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_w:
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
