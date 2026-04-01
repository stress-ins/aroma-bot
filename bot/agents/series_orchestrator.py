"""Series Orchestrator agent: generates an outline for a content series."""

from __future__ import annotations

import logging
import re

from bot.utils.json_parser import extract_json

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
    """Parse outline from Claude JSON response.

    Falls back to legacy text parsing if JSON extraction fails.
    """
    # Try JSON parsing first
    try:
        data = extract_json(raw)
        if isinstance(data, dict):
            return _map_json_outline(data, expected_count, topic)
    except (ValueError, TypeError):
        logger.warning("series_orchestrator: JSON parsing failed, trying legacy text parser")

    return _parse_outline_legacy(raw, expected_count, topic)


def _map_json_outline(data: dict, expected_count: int, topic: str) -> dict:
    """Map parsed JSON outline to expected format."""
    summary = data.get("summary", "")
    raw_positions = data.get("positions", [])

    positions = []
    for item in raw_positions:
        if not isinstance(item, dict):
            continue
        try:
            idx = int(item.get("index", 0))
        except (ValueError, TypeError):
            idx = 0
        if idx >= 1:
            idx -= 1  # Convert 1-based to 0-based
        role = str(item.get("role", "middle")).lower()
        if role not in ("intro", "middle", "climax", "cta"):
            role = "middle"
        positions.append({
            "index": idx,
            "title": item.get("title", f"Пост {idx + 1}"),
            "angle": item.get("angle", ""),
            "role": role,
        })

    return _finalize_outline(positions, expected_count, topic, summary)


def _parse_outline_legacy(raw: str, expected_count: int, topic: str) -> dict:
    """Legacy parser: extract outline from POST N: text markers."""
    positions = []
    summary = ""

    current_post = None
    for line in raw.strip().splitlines():
        line = line.strip()
        if not line:
            continue

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

    return _finalize_outline(positions, expected_count, topic, summary)


def _finalize_outline(positions: list[dict], expected_count: int, topic: str, summary: str) -> dict:
    """Ensure correct count and enforce role constraints."""
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
