"""Tone Adapter agent: rewrite post content in a different tone."""

from __future__ import annotations

import logging

from bot.services.humanizer import humanize

logger = logging.getLogger(__name__)

VALID_TONES = ("educational", "inspirational", "selling", "storytelling")


def adapt_tone_sync(
    text: str,
    tone_key: str,
    topic: str,
    format_key: str = "instagram",
) -> dict:
    """Adapt post text to the specified tone.

    Returns dict with: tone, adapted_text, quality_score.
    """
    from bot.agents.creative_team import edit_post_sync
    from bot.agents.prompts.tone_prompts import TONE_DEFINITIONS, adapt_tone_prompt
    from bot.services.claude_client import call_claude

    if tone_key not in TONE_DEFINITIONS:
        raise ValueError(f"Unknown tone: {tone_key}. Valid: {VALID_TONES}")

    prompt = adapt_tone_prompt(text, tone_key, topic, format_key)

    raw = call_claude(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=900,
        context=f"tone_adapter:{tone_key}",
    )

    adapted = humanize(raw.strip())

    # Editor pass
    try:
        adapted = edit_post_sync(adapted, topic, platform=format_key)
    except Exception:
        logger.warning("Editor pass failed for tone %s, using raw", tone_key)

    # Quality evaluation
    quality_score = None
    try:
        from bot.agents.quality_evaluator import _evaluate_sync
        quality_score = _evaluate_sync(adapted, format_key, topic)
    except Exception:
        logger.warning("Quality eval failed for tone %s", tone_key)

    tone_def = TONE_DEFINITIONS[tone_key]
    return {
        "tone": tone_key,
        "label": tone_def["label"],
        "adapted_text": adapted,
        "quality_score": quality_score,
    }


def get_tone_labels() -> dict[str, str]:
    """Return {tone_key: label} mapping."""
    from bot.agents.prompts.tone_prompts import TONE_DEFINITIONS
    return {k: v["label"] for k, v in TONE_DEFINITIONS.items()}
