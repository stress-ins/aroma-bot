"""UX Reviewer agent — evaluates aroma reference card content quality."""
from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

KNOWN_SOURCE_TYPES = {"herb", "flower", "resin", "tree", "spice", "citrus", "grass", "root", "wood"}


def _check_card_fields(card: dict[str, Any]) -> tuple[float, list[str]]:
    """Pure synchronous checklist evaluation of card fields (no LLM call).

    Returns:
        (score 0.0–1.0, list of issue descriptions)
    """
    issues: list[str] = []
    score = 1.0
    penalty = 0.15

    description_short = str(card.get("description_short") or "").strip()
    description = str(card.get("description") or "").strip()
    applications = str(card.get("applications") or "").strip()
    source_type = str(card.get("source_type") or "").strip().lower()
    comp_slugs = card.get("complementary_oil_slugs") or []
    comp_names = card.get("complementary_oil_names") or []
    name = str(card.get("name") or "").strip()

    if not name:
        issues.append("name is empty")
        score -= penalty

    if description and not description_short:
        issues.append("description_short is empty but description is present")
        score -= penalty

    if description_short and len(description_short) > 280:
        issues.append(f"description_short is too long ({len(description_short)} chars, max 280)")
        score -= penalty * 0.5

    if description_short and description and description_short == description:
        issues.append("description_short is identical to description — not summarized")
        score -= penalty

    if description_short:
        if description_short.endswith("...") or description_short.endswith("{") or description_short.endswith('"'):
            issues.append("description_short appears truncated (ends with artifact)")
            score -= penalty
        if description_short.strip().startswith("{"):
            issues.append("description_short looks like raw JSON (starts with '{')")
            score -= penalty
        else:
            try:
                json.loads(description_short)
                issues.append("description_short is raw JSON, not human-readable text")
                score -= penalty
            except (ValueError, TypeError):
                pass

    if not applications:
        issues.append("applications field is empty")
        score -= penalty * 0.5

    if source_type and source_type not in KNOWN_SOURCE_TYPES:
        issues.append(f"source_type '{source_type}' is not a known value ({', '.join(sorted(KNOWN_SOURCE_TYPES))})")
        score -= penalty * 0.5

    if isinstance(comp_slugs, list) and isinstance(comp_names, list):
        if len(comp_slugs) != len(comp_names):
            issues.append(
                f"complementary_oil_slugs ({len(comp_slugs)}) and _names ({len(comp_names)}) have different lengths"
            )
            score -= penalty * 0.3

    return max(0.0, round(score, 2)), issues


async def review_card_ux(card_data: dict[str, Any]) -> dict[str, Any]:
    """Evaluate rendered card UX against a checklist.

    Args:
        card_data: Serialized card dict (as returned by get_reference_card / _serialize_model).

    Returns:
        {"passed": bool, "score": float, "issues": list[str]}
    """
    score, issues = _check_card_fields(card_data)
    passed = score >= 0.7 and len(issues) == 0
    return {"passed": passed, "score": score, "issues": issues}
