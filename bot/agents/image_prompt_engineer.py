"""Image Prompt Engineer Agent — consistent, high-quality image prompts for Gemini/NanoBanana."""
from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)

# ── Brand palette ────────────────────────────────────────────────────────────
BRAND_PALETTE = {
    "terracotta": "#C4956A",
    "sage_green": "#6B8F71",
    "warm_beige": "#F5F0EB",
    "soft_purple": "#8B7DB8",
}

STYLE_PRESETS: dict[str, str] = {
    "botanical_wellness": (
        "soft natural lighting, botanical elements, warm tones, minimalist composition, "
        "dried flowers, herbs, natural textures, linen fabric, terracotta ceramics, "
        "shallow depth of field, 85mm lens equivalent"
    ),
    "minimal_modern": (
        "clean lines, generous negative space, editorial feel, muted color palette, "
        "geometric balance, studio lighting, modernist aesthetic, 50mm lens equivalent"
    ),
    "warm_editorial": (
        "warm golden hour lighting, cozy atmosphere, lifestyle photography feel, "
        "candlelight or window light, inviting composition, layered textures, "
        "soft bokeh background, 35mm lens equivalent"
    ),
}

DEFAULT_NEGATIVE_PROMPTS = [
    "no text",
    "no watermarks",
    "no logos",
    "no faces",
    "no hands",
    "no distortion",
    "no typography",
    "no words",
]

ASPECT_RATIO_LABELS: dict[str, str] = {
    "9:16": "vertical portrait composition for Reels/Stories",
    "1:1": "square composition for carousel slides",
    "4:5": "portrait composition for Instagram feed posts",
}

_SYSTEM = """\
You are an expert Image Prompt Engineer specializing in brand-consistent visual content.

Your task: given a scene description and style parameters, craft a professional image \
generation prompt optimized for AI image generators (Gemini Imagen, Midjourney-style).

BRAND PALETTE (always incorporate):
- Terracotta (#C4956A) — warm clay tones
- Sage green (#6B8F71) — muted botanical greens
- Warm beige (#F5F0EB) — soft neutral backgrounds
- Soft purple (#8B7DB8) — accent lavender tones

STYLE PRESETS:
- botanical_wellness: {botanical_wellness}
- minimal_modern: {minimal_modern}
- warm_editorial: {warm_editorial}

PHOTOGRAPHY DIRECTION RULES:
1. Always specify lens type (35mm, 50mm, 85mm, macro)
2. Always specify lighting (natural, golden hour, studio, candlelight, soft diffused)
3. Always specify depth of field (shallow bokeh, medium, deep)
4. Use cinematic / editorial vocabulary
5. Include specific objects and textures, not abstract concepts

OUTPUT FORMAT — return ONLY valid JSON (no markdown fences, no extra text):
{{
  "prompt": "the main image generation prompt in English",
  "negative_prompt": "comma-separated list of things to avoid",
  "style_tags": ["keyword1", "keyword2", ...],
  "aspect_ratio": "W:H"
}}

MANDATORY NEGATIVE PROMPTS (always include these plus any user-specified):
no text, no watermarks, no logos, no faces, no hands, no distortion, no typography, no words
"""

_USER_TEMPLATE = """\
Scene description: {scene_description}
Style preset: {style}
Aspect ratio: {aspect_ratio} — {aspect_label}
{extra_negative_block}
Craft the image prompt now. Return ONLY valid JSON."""


def _build_system_prompt() -> str:
    return _SYSTEM.format(**STYLE_PRESETS)


def _parse_response(raw: str) -> dict | None:
    """Parse JSON from Claude response, handling possible markdown wrapping."""
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
        text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Image Prompt Engineer: failed to parse JSON: %s", text[:300])
        return None


def craft_image_prompt_sync(
    scene_description: str,
    style: str = "botanical_wellness",
    aspect_ratio: str = "9:16",
    negative_prompts: list[str] | None = None,
) -> dict:
    """Craft a professional image generation prompt.

    Returns {
        "prompt": str,           # The main prompt
        "negative_prompt": str,   # What to avoid
        "style_tags": [str],      # Style keywords
        "aspect_ratio": str       # e.g. "9:16"
    }
    """
    from bot.services.claude_client import call_claude

    if style not in STYLE_PRESETS:
        style = "botanical_wellness"

    aspect_label = ASPECT_RATIO_LABELS.get(aspect_ratio, f"{aspect_ratio} composition")

    extra_negative_block = ""
    if negative_prompts:
        extra_negative_block = (
            "Additional negative prompts: " + ", ".join(negative_prompts)
        )

    user_msg = _USER_TEMPLATE.format(
        scene_description=scene_description,
        style=style,
        aspect_ratio=aspect_ratio,
        aspect_label=aspect_label,
        extra_negative_block=extra_negative_block,
    )

    raw = call_claude(
        messages=[{"role": "user", "content": user_msg}],
        max_tokens=600,
        system=_build_system_prompt(),
        context="image prompt engineer",
    )

    parsed = _parse_response(raw)

    if parsed is None:
        # Fallback: build a reasonable prompt from inputs
        style_desc = STYLE_PRESETS.get(style, STYLE_PRESETS["botanical_wellness"])
        all_negatives = list(DEFAULT_NEGATIVE_PROMPTS)
        if negative_prompts:
            all_negatives.extend(negative_prompts)
        return {
            "prompt": (
                f"{scene_description}, {style_desc}, "
                f"brand palette terracotta beige sage green soft purple, "
                f"{aspect_label}"
            ),
            "negative_prompt": ", ".join(all_negatives),
            "style_tags": [style, "brand_palette", "atmospheric"],
            "aspect_ratio": aspect_ratio,
        }

    # Ensure all required fields present
    parsed.setdefault("prompt", scene_description)
    parsed.setdefault("negative_prompt", ", ".join(DEFAULT_NEGATIVE_PROMPTS))
    parsed.setdefault("style_tags", [style])
    parsed.setdefault("aspect_ratio", aspect_ratio)

    # Ensure mandatory negatives are present
    neg_lower = parsed["negative_prompt"].lower()
    for mandatory in DEFAULT_NEGATIVE_PROMPTS:
        if mandatory not in neg_lower:
            parsed["negative_prompt"] += f", {mandatory}"

    return parsed
