from __future__ import annotations

from bot.agents import ContentDraft
from bot.agents.reels_agent import StoryboardFrame


CONTENT_GOAL_OPTIONS = {"trust", "authority", "engagement", "sales"}
CONTENT_FORMAT_OPTIONS = {"threads", "instagram", "telegram"}


def is_valid_content_goal(goal_key: str) -> bool:
    return goal_key in CONTENT_GOAL_OPTIONS


def is_valid_content_format(format_key: str) -> bool:
    return format_key in CONTENT_FORMAT_OPTIONS


def build_content_payload(draft: ContentDraft) -> dict[str, object]:
    return {
        "angle": draft.angle,
        "hook": draft.hook,
        "caption": draft.caption,
        "cta": draft.cta,
        "hashtags": draft.hashtags,
        "visual_prompt": draft.visual_prompt,
        "slides": list(draft.slides),
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
