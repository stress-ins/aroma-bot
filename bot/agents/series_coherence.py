"""Series Coherence Editor: checks narrative coherence of the series."""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


def check_coherence_sync(
    topic: str,
    posts: list[dict],
) -> dict:
    """Check coherence of a content series.

    Returns dict with: score (float 0-1), issues (list[str]), suggestion (str).
    """
    from bot.agents.prompts.series_prompts import coherence_prompt
    from bot.services.claude_client import call_claude

    posts_text = _format_posts_for_review(posts)

    prompt = coherence_prompt(topic, posts_text, len(posts))

    raw = call_claude(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=400,
        context="series_coherence",
    )

    return _parse_coherence(raw)


def _format_posts_for_review(posts: list[dict]) -> str:
    """Format posts for coherence review."""
    lines = []
    for p in posts:
        idx = p.get("index", 0) + 1
        role = p.get("role", "middle")
        title = p.get("title", f"Пост {idx}")
        caption = p.get("caption", "")
        lines.append(f"--- Пост {idx} ({role}): {title} ---\n{caption}\n")
    return "\n".join(lines)


def _parse_coherence(raw: str) -> dict:
    """Parse coherence check response."""
    score = 0.7
    issues = []
    suggestion = ""

    for line in raw.strip().splitlines():
        line = line.strip()
        cleaned = line.replace("**", "").strip()

        if cleaned.upper().startswith("SCORE:"):
            try:
                val = cleaned.split(":", 1)[1].strip()
                val = re.sub(r"[^\d.]", "", val)
                score = float(val)
                score = max(0.0, min(1.0, score))
            except (ValueError, IndexError):
                logger.warning("_parse_coherence: split failed", exc_info=True)
                pass
        elif cleaned.upper().startswith("ISSUES:"):
            raw_issues = cleaned.split(":", 1)[1].strip()
            if raw_issues.lower() not in ("нет", "none", ""):
                issues = [i.strip() for i in raw_issues.split(";") if i.strip()]
        elif cleaned.upper().startswith("SUGGESTION:"):
            suggestion = cleaned.split(":", 1)[1].strip()
            if suggestion.lower() in ("нет", "none"):
                suggestion = ""

    return {
        "score": round(score, 2),
        "issues": issues,
        "suggestion": suggestion,
    }
