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

    posts = split_threads_posts(draft.caption, template=template) if draft.caption else []
    default_times = template["default_times"] if template else {"morning": "08:54", "day": "13:12", "evening": "20:30"}

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
