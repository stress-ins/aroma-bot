"""Image Prompt Router — model-aware prompt optimization.

Replaces the single-model nanobanana_prompt_expert with a registry
of model profiles, each with its own system prompt and constraints.
"""
from __future__ import annotations

import re

_GPT_IMAGE_SYSTEM = (
    "You are a prompt engineer for GPT Image 1.5 (text-to-image).\n"
    "Take the raw art-director brief and rewrite it as a CONCISE image prompt (50-100 words).\n\n"
    "Rules:\n"
    "1. Structure: subject → composition → lighting → palette → mood.\n"
    "2. Use concrete nouns and adjectives. No film references, no lens specs, no grain.\n"
    "3. Color palette must match the topic mood — never default to one palette.\n"
    "4. Composition: 'vertical 4:5, generous negative space for text overlay'.\n"
    "5. Quality: 'professional editorial photography, sharp detail'.\n"
    "6. Negative: 'no text, no watermarks, no human faces, no visible hands'.\n"
    "7. If a user_note is provided, integrate it naturally.\n"
    "8. REMOVE any Midjourney/SD parameters (--ar, --style, --v, etc.).\n"
    "9. Output ONLY the final prompt — no commentary, no markdown.\n"
    "{blend_mood_block}"
)

_NANOBANANA_SYSTEM = (
    "You are a world-class prompt engineer specialising in photorealistic image generation "
    "for the NanoBanana API. Your job is to take a short art-director brief and expand it "
    "into a rich, detailed image prompt (150-400 words).\n\n"
    "Rules:\n"
    "1. Expand the scene description with vivid, specific details — materials, textures, "
    "surfaces, objects, spatial relationships.\n"
    "2. Describe the COLOR PALETTE in words derived from the topic mood — never hardcode a "
    "single palette for all topics.\n"
    "3. Add LIGHTING description: type (golden hour / soft diffused / directional / "
    "candlelit / etc.), quality, direction, shadows.\n"
    "4. Add LENS / DEPTH OF FIELD: shallow DoF, macro, wide-angle, 85mm portrait, etc.\n"
    "5. Add FILM AESTHETIC if fitting: Kodak Portra, Fuji Velvia, matte film grain, etc.\n"
    "6. Add COMPOSITION instruction: 'vertical portrait composition, 4:5 aspect ratio, "
    "generous negative space at bottom third for text overlay'.\n"
    "7. Add QUALITY BOOSTERS: 'professional editorial photography, high resolution, "
    "sharp detail, rich saturated tones'.\n"
    "8. Add NEGATIVE DESCRIPTIONS directly in the prompt text: 'absolutely no text, "
    "no watermarks, no human faces, no visible hands'.\n"
    "9. If a user_note is provided, integrate it NATURALLY into the prompt — do NOT just "
    "append it at the end.\n"
    "10. REMOVE any Midjourney or Stable Diffusion parameters (--ar, --style, --v, --no, "
    "--s, --q, etc.) — these are NOT supported.\n"
    "11. Output ONLY the final prompt text — no commentary, no markdown, no labels.\n"
    "{blend_mood_block}"
)

_NANOBANANA_EDIT_SYSTEM = (
    "You are a prompt engineer for image-to-image editing via NanoBanana Edit.\n"
    "You receive a base image prompt and must rewrite it to focus on WHAT TO CHANGE.\n\n"
    "Rules:\n"
    "1. Focus on the edit intent: what should change vs what stays.\n"
    "2. Keep the prompt 100-200 words.\n"
    "3. Describe desired modifications: palette shift, mood change, element add/remove.\n"
    "4. Preserve composition references from the original.\n"
    "5. Color palette adjustments should match the topic mood.\n"
    "6. If a user_note is provided, treat it as the PRIMARY edit instruction.\n"
    "7. REMOVE any Midjourney/SD parameters.\n"
    "8. Output ONLY the final prompt — no commentary, no markdown.\n"
    "{blend_mood_block}"
)

MODEL_PROFILES: dict[str, dict] = {
    "gpt-image/1.5-text-to-image": {
        "type": "text-to-image",
        "system": _GPT_IMAGE_SYSTEM,
        "max_tokens": 300,
    },
    "google/nano-banana": {
        "type": "text-to-image",
        "system": _NANOBANANA_SYSTEM,
        "max_tokens": 600,
    },
    "google/nano-banana-edit": {
        "type": "img2img",
        "system": _NANOBANANA_EDIT_SYSTEM,
        "max_tokens": 500,
    },
}

# Fallback profile for unknown models
_DEFAULT_PROFILE = {
    "type": "text-to-image",
    "system": _NANOBANANA_SYSTEM,
    "max_tokens": 600,
}


def optimize_image_prompt(
    raw_prompt: str,
    model: str,
    *,
    topic: str = "",
    slide_number: int = 0,
    total_slides: int = 1,
    user_note: str = "",
    blend_mood: str | None = None,
) -> str:
    """Route to model-specific prompt optimization.

    Parameters
    ----------
    raw_prompt : str
        Short art-director prompt (30-50 words).
    model : str
        Model identifier, e.g. "gpt-image/1.5-text-to-image".
    topic : str
        Overall topic of the content piece.
    slide_number : int
        Zero-based slide/frame index.
    total_slides : int
        Total number of slides/frames.
    user_note : str
        Optional revision note from the user.
    blend_mood : str | None
        Visual directive from blend profile (palette, lighting, mood).
    """
    from bot.services.claude_client import call_claude

    profile = MODEL_PROFILES.get(model, _DEFAULT_PROFILE)

    blend_mood_block = ""
    if blend_mood:
        blend_mood_block = (
            "\n\nBLEND VISUAL MOOD (use as PRIMARY visual driver):\n"
            f"{blend_mood}\n"
            "Integrate this palette and botanical elements as the dominant visual theme.\n"
        )

    system = profile["system"].format(blend_mood_block=blend_mood_block)

    note_part = f"\nUser revision note (integrate naturally): {user_note}" if user_note.strip() else ""

    user_msg = (
        f"Topic: {topic}\n"
        f"Slide {slide_number + 1} of {total_slides}\n"
        f"Raw art-director prompt: {raw_prompt}"
        f"{note_part}\n\n"
        "Rewrite this into an optimized image prompt following the rules."
    )

    result = call_claude(
        messages=[{"role": "user", "content": user_msg}],
        max_tokens=profile["max_tokens"],
        system=system,
        context="image_prompt_router",
    )

    # Strip any residual MJ/SD flags
    result = re.sub(r"--\w+\s+\S*", "", result).strip()
    return result
