"""Series Orchestrator agent: generates an outline for a content series."""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


def generate_outline_sync(
    topic: str,
    goal_key: str,
    format_key: str,
    post_count: int,
    template_hint: str,
    goal_guidance: dict[str, str],
    format_labels: dict[str, str],
    rag_context: str = "",
) -> dict:
    """Generate series outline via Claude.

    Returns dict with keys: theme, summary, positions[{index, title, angle, role}].
    """
    from bot.agents.prompts.series_prompts import outline_prompt
    from bot.services.claude_client import call_claude

    prompt = outline_prompt(
        topic, goal_key, format_key, post_count, template_hint,
        goal_guidance, format_labels, rag_context=rag_context,
    )

    raw = call_claude(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=500,
        context="series_orchestrator",
    )

    return _parse_outline(raw, post_count, topic)


def _parse_outline(raw: str, expected_count: int, topic: str) -> dict:
    """Parse outline from Claude response."""
    positions = []
    summary = ""

    current_post = None
    for line in raw.strip().splitlines():
        line = line.strip()
        if not line:
            continue

        # POST N: title
        m = re.match(r"POST\s+(\d+)\s*:\s*(.+)", line, re.IGNORECASE)
        if m:
            if current_post is not None:
                positions.append(current_post)
            idx = int(m.group(1)) - 1
            current_post = {
                "index": idx,
                "title": m.group(2).strip(),
                "angle": "",
                "role": "middle",
            }
            continue

        if current_post is not None:
            cleaned = line.replace("**", "").strip()
            if cleaned.upper().startswith("ANGLE:"):
                current_post["angle"] = cleaned.split(":", 1)[1].strip()
            elif cleaned.upper().startswith("ROLE:"):
                role = cleaned.split(":", 1)[1].strip().lower()
                if role in ("intro", "middle", "climax", "cta"):
                    current_post["role"] = role

        if line.upper().startswith("SUMMARY:"):
            summary = line.split(":", 1)[1].strip()

    if current_post is not None:
        positions.append(current_post)

    # Ensure we have the right count, fill missing with defaults
    while len(positions) < expected_count:
        idx = len(positions)
        role = "middle"
        if idx == 0:
            role = "intro"
        elif idx == expected_count - 1:
            role = "cta"
        elif idx == expected_count - 2:
            role = "climax"
        positions.append({
            "index": idx,
            "title": f"Пост {idx + 1}",
            "angle": "",
            "role": role,
        })

    # Enforce role constraints
    if positions:
        positions[0]["role"] = "intro"
        positions[-1]["role"] = "cta"
        if len(positions) >= 3:
            positions[-2]["role"] = "climax"

    return {
        "theme": topic,
        "summary": summary or f"Серия из {expected_count} постов на тему: {topic}",
        "positions": positions[:expected_count],
    }
