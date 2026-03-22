"""Repurpose Agent: extract core ideas from a post for multi-format adaptation."""

from __future__ import annotations

import logging

from bot.services.humanizer import humanize

logger = logging.getLogger(__name__)

VALID_FORMATS = ("carousel", "reels_v2", "threads_series", "instagram", "telegram")


def extract_core_ideas_sync(text: str, topic: str) -> dict:
    """Extract core message and key points from source post.

    Returns: {core_message, key_points, tone, target_audience}.
    """
    from bot.services.claude_client import call_claude

    prompt = f"""\
Проанализируй текст поста и извлеки ключевые элементы для адаптации в другие форматы.

Тема: {topic}
Текст:
{text[:2000]}

Верни строго в формате:
CORE: [главная мысль поста в 1-2 предложениях]
POINTS: [3-5 ключевых тезисов через точку с запятой]
TONE: [тон поста: educational/inspirational/selling/storytelling]
AUDIENCE: [целевая аудитория в 1 предложении]"""

    raw = call_claude(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=400,
        context="repurpose_extract",
    )

    result = {"core_message": "", "key_points": [], "tone": "", "target_audience": ""}
    for line in raw.strip().splitlines():
        line = line.strip().replace("**", "")
        if line.upper().startswith("CORE:"):
            result["core_message"] = humanize(line.split(":", 1)[1].strip())
        elif line.upper().startswith("POINTS:"):
            points_raw = line.split(":", 1)[1].strip()
            result["key_points"] = [p.strip() for p in points_raw.split(";") if p.strip()]
        elif line.upper().startswith("TONE:"):
            result["tone"] = line.split(":", 1)[1].strip().lower()
        elif line.upper().startswith("AUDIENCE:"):
            result["target_audience"] = line.split(":", 1)[1].strip()

    if not result["core_message"]:
        result["core_message"] = text[:200]

    return result
