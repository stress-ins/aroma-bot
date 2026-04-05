from __future__ import annotations

from bot.agents import ContentDraft
from bot.agents.content import split_threads_posts
from bot.agents.reels_agent import StoryboardFrame


CONTENT_GOAL_OPTIONS = {"trust", "authority", "engagement", "sales"}
CONTENT_FORMAT_OPTIONS = {"instagram", "telegram", "threads_series"}


def is_valid_content_goal(goal_key: str) -> bool:
    return goal_key in CONTENT_GOAL_OPTIONS


def is_valid_content_format(format_key: str) -> bool:
    return format_key in CONTENT_FORMAT_OPTIONS


def build_content_payload(draft: ContentDraft, *, goal_key: str, format_key: str) -> dict[str, object]:
    payload: dict[str, object] = {
        "goal_key": goal_key,
        "format_key": format_key,
        "angle": draft.angle,
        "hook": draft.hook,
        "caption": draft.caption,
        "cta": draft.cta,
        "hashtags": draft.hashtags,
        "visual_prompt": draft.visual_prompt,
        "stock_keywords": list(draft.stock_keywords),
        "slides": list(draft.slides),
    }

    return payload


def build_threads_series_payload(
    draft: ContentDraft,
    *,
    goal_key: str,
    emotion: str = "",
) -> dict[str, object]:
    """Build rich payload for threads_series kind with per-slot status and version history."""
    from bot.agents.content import SERIES_TEMPLATES

    # Resolve the template used for this draft
    template = None
    template_key = getattr(draft, "series_template_key", "") or ""
    if template_key and template_key in SERIES_TEMPLATES:
        template = SERIES_TEMPLATES[template_key]

    # Use structured JSON posts if available; fall back to text marker parsing
    if draft.threads_posts:
        posts = _map_structured_posts_to_slots(draft.threads_posts, template)
    else:
        posts = split_threads_posts(draft.caption, template=template) if draft.caption else []

    default_times = template["default_times"] if template else {"morning": "08:54", "day": "13:12", "evening": "20:30"}
    # Also check for dynamic times from generation
    series_tmpl = getattr(draft, "_series_template", None)
    if series_tmpl and series_tmpl.get("default_times"):
        default_times = series_tmpl["default_times"]

    threads_posts: list[dict[str, object]] = []
    for post in posts:
        threads_posts.append({
            "slot": post["slot"],
            "label": post["label"],
            "text": post["text"],
            "why_it_works": post.get("why_it_works", ""),
            "scheduled_time": default_times.get(post["slot"], "12:00"),
            "status": "draft",
            "error_message": None,
            "versions": [],
            "icon": post.get("icon", ""),
        })
    return {
        "goal": goal_key,
        "emotion": emotion,
        "series_summary": draft.angle or "",
        "series_template": template_key,
        "series_template_name": template["name"] if template else "Утро / День / Вечер",
        "threads_posts": threads_posts,
        "generation_pending": False,
    }


def _map_structured_posts_to_slots(
    json_posts: list[dict],
    template: dict | None,
) -> list[dict]:
    """Map JSON posts (with marker/text/why_it_works) to slot definitions from template."""
    from bot.agents.content import SERIES_TEMPLATES, _detect_template_from_caption

    # Build marker → slot mapping from template
    if template:
        slots_def = template["slots"]
    else:
        # Try to detect template from markers in the JSON posts
        markers_text = "\n".join(p.get("marker", "") for p in json_posts)
        detected = _detect_template_from_caption(markers_text)
        slots_def = detected["slots"]

    marker_to_slot = {s["marker"].upper(): s for s in slots_def}
    result: list[dict] = []

    for i, jp in enumerate(json_posts):
        marker = jp.get("marker", "").strip().upper()
        slot_info = marker_to_slot.get(marker)
        if slot_info:
            result.append({
                "slot": slot_info["slot"],
                "label": slot_info["label"],
                "text": jp.get("text", ""),
                "why_it_works": jp.get("why_it_works", ""),
                "icon": slot_info.get("icon", ""),
            })
        else:
            # Unknown marker — create a numbered slot
            slot_id = f"post_{i + 1}"
            result.append({
                "slot": slot_id,
                "label": marker or f"ПОСТ {i + 1}",
                "text": jp.get("text", ""),
                "why_it_works": jp.get("why_it_works", ""),
                "icon": "",
            })
    return result


def build_reels_payload(topic: str, scenario: str, frames: list[StoryboardFrame]) -> dict[str, object]:
    return {
        "topic": topic,
        "scenario": scenario,
        "storyboard": [
            {
                "timecode": frame.timecode,
                "scene": frame.scene,
                "angle": frame.angle,
                "gemini_prompt": frame.gemini_prompt,
            }
            for frame in frames
        ],
        "images_ready": 0,
    }
