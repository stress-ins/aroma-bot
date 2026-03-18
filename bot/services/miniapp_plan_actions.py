from __future__ import annotations


def normalize_plan_goal(goal_label: str) -> str:
    value = goal_label.strip().lower()
    if "прод" in value:
        return "sales"
    if "вовл" in value:
        return "engagement"
    if "эксперт" in value:
        return "authority"
    return "trust"


def normalize_plan_format(entry: dict[str, str]) -> str:
    platform = entry.get("platform", "").strip().lower()
    format_label = entry.get("format_label", "").strip().lower()

    if "reels" in platform or "reels" in format_label or "рилс" in format_label:
        return "reels"
    if "карус" in format_label or "carousel" in format_label:
        return "carousel"
    if "threads" in platform:
        return "threads_series"
    if "instagram" in platform:
        return "instagram"
    if "telegram" in platform:
        return "telegram"
    return "instagram"
