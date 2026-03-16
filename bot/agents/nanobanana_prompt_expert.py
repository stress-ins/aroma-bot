"""NanoBanana Prompt Expert — optimizes raw art-director prompts for the NanoBanana image API."""
from __future__ import annotations

import re


def optimize_prompt_for_nanobanana(
    raw_prompt: str,
    topic: str,
    slide_number: int,
    total_slides: int,
    user_note: str = "",
) -> str:
    """Take a short art-director prompt and expand it into a detailed NanoBanana-ready prompt.

    The result is 150-400 words with lighting, lens, palette, composition, quality
    boosters and negative descriptions baked in.  Any Midjourney/SD parameters are
    stripped.
    """
    from bot.services.claude_client import call_claude

    system = (
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
        "11. Output ONLY the final prompt text — no commentary, no markdown, no labels."
    )

    note_part = f"\nUser revision note (integrate naturally): {user_note}" if user_note.strip() else ""

    user_msg = (
        f"Topic of the carousel: {topic}\n"
        f"Slide {slide_number + 1} of {total_slides}\n"
        f"Raw art-director prompt: {raw_prompt}"
        f"{note_part}\n\n"
        "Expand this into a detailed NanoBanana image prompt following the rules."
    )

    result = call_claude(
        messages=[{"role": "user", "content": user_msg}],
        max_tokens=600,
        system=system,
        context="nanobanana_prompt_expert",
    )

    # Strip any residual MJ/SD flags
    result = re.sub(r"--\w+\s+\S*", "", result).strip()
    return result
