"""Platform Optimizer Agent — algorithm-aware content optimization."""
from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)

_PLATFORM_KNOWLEDGE: dict[str, str] = {
    "instagram": (
        "Platform: Instagram\n"
        "- Reels: first 3 seconds are critical for retention\n"
        "- Reels: text on screen is required for accessibility and engagement\n"
        "- Reels: trending audio boosts reach significantly\n"
        "- Reels: 15-30 seconds is the optimal duration\n"
        "- Posts: 4:5 aspect ratio performs best in feed\n"
        "- Posts: carousel > single image (more time on post = algorithm boost)\n"
        "- Posts: first slide must stop the scroll\n"
        "- Captions: front-load value, hashtags at end (5-10)\n"
        "- Stories: polls and questions boost engagement metrics"
    ),
    "tiktok": (
        "Platform: TikTok\n"
        "- 7-15 seconds is currently trending for maximum completion rate\n"
        "- Duet/stitch hooks drive discovery\n"
        "- Text overlay should be in center (safe zone)\n"
        "- Trending sounds dramatically boost reach\n"
        "- First frame must be visually compelling (thumbnail)\n"
        "- Loop potential: ending that flows into the beginning\n"
        "- Comments and saves are the strongest algorithm signals\n"
        "- Niche hashtags (3-5) outperform broad ones"
    ),
    "threads": (
        "Platform: Threads (Meta)\n"
        "- First line is everything: must stop the scroll in under 2 seconds\n"
        "- Controversial or counterintuitive takes drive replies and shares\n"
        "- Series of 3 posts perform better than single posts (algorithm rewards consecutive engagement)\n"
        "- Questions at the end boost reply rate significantly\n"
        "- No hashtags needed — discovery is algorithmic, not hashtag-based\n"
        "- Short posts (40-80 words) outperform long ones\n"
        "- Personal stories and 'hot takes' get the most engagement\n"
        "- Replies to own posts within 30 min boost visibility\n"
        "- Saves and shares are stronger signals than likes"
    ),
    "threads_series": (
        "Platform: Threads (Meta) — Series of 3 posts\n"
        "- First line is everything: must stop the scroll in under 2 seconds\n"
        "- Series format: each post should stand alone but connect to the next\n"
        "- Variety in structure (not always same pattern) keeps audience engaged\n"
        "- Questions and calls to reply drive algorithm boost\n"
        "- Personal vulnerability and specific situations outperform generic advice\n"
        "- Short posts (40-80 words) outperform long ones\n"
        "- No hashtags — algorithm handles discovery\n"
        "- Posting with 4-6 hour gaps between series posts is optimal\n"
        "- Saves and shares are stronger signals than likes"
    ),
}

_CONTENT_TYPE_CONTEXT: dict[str, str] = {
    "post": "This is a text/image post for the feed.",
    "reels": "This is a short-form vertical video (Reels/TikTok).",
    "carousel": "This is a multi-slide carousel post.",
}

_SYSTEM = """\
You are a Platform Algorithm Optimizer — an expert in social media algorithms and \
content optimization for maximum reach and engagement.

{platform_knowledge}

Content type: {content_type_context}

Your task: analyze the given content and provide specific, actionable optimizations \
to maximize algorithmic reach and engagement on this platform.

Evaluate:
1. ALGORITHM ALIGNMENT — does the content match what the algorithm promotes?
2. HOOK STRENGTH — will it stop the scroll / retain viewers?
3. ENGAGEMENT TRIGGERS — does it invite comments, saves, shares?
4. HASHTAG STRATEGY — right hashtags for discovery (if applicable)
5. POSTING TIMING — best time to post this type of content
6. PREDICTED PERFORMANCE — realistic engagement tier

OUTPUT FORMAT — return ONLY valid JSON (no markdown fences, no extra text):
{{
  "platform": "{platform}",
  "algorithm_score": 0-10,
  "optimizations": [
    {{"type": "hook|length|format|cta|structure|tone", "current": "what it is now", "suggested": "what to change", "impact": "high|medium|low"}}
  ],
  "hashtag_suggestions": ["tag1", "tag2"],
  "posting_time_suggestion": "description of best posting window",
  "predicted_engagement_tier": "viral|high|medium|low",
  "hooks_analysis": {{
    "has_hook": true/false,
    "hook_strength": "strong|moderate|weak|none",
    "suggestion": "how to improve the hook"
  }}
}}
"""

_USER_TEMPLATE = """\
Analyze and optimize this content for {platform} ({content_type}):

{text}

Provide platform-specific optimization. Return ONLY valid JSON."""


def _parse_response(raw: str) -> dict | None:
    """Parse JSON from Claude response, handling possible markdown wrapping."""
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
        text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Platform Optimizer: failed to parse JSON: %s", text[:300])
        return None


_FALLBACK_TEMPLATE: dict = {
    "platform": "",
    "algorithm_score": 5.0,
    "optimizations": [],
    "hashtag_suggestions": [],
    "posting_time_suggestion": "",
    "predicted_engagement_tier": "medium",
    "hooks_analysis": {
        "has_hook": False,
        "hook_strength": "none",
        "suggestion": "",
    },
}


def optimize_for_platform_sync(
    text: str,
    platform: str,
    content_type: str = "post",
) -> dict:
    """Evaluate and optimize content for platform algorithm.

    Args:
        text: The content to optimize.
        platform: Target platform — "threads", "instagram", or "tiktok".
        content_type: Content format — "post", "reels", or "carousel".

    Returns {
        "platform": str,
        "algorithm_score": float,  # 0-10
        "optimizations": [{"type": str, "current": str, "suggested": str, "impact": str}],
        "hashtag_suggestions": [str],
        "posting_time_suggestion": str,
        "predicted_engagement_tier": str,  # "viral" | "high" | "medium" | "low"
        "hooks_analysis": {"has_hook": bool, "hook_strength": str, "suggestion": str}
    }
    """
    from bot.services.claude_client import call_claude

    # Normalize inputs
    if platform not in _PLATFORM_KNOWLEDGE:
        platform = "instagram"
    if content_type not in _CONTENT_TYPE_CONTEXT:
        content_type = "post"

    platform_knowledge = _PLATFORM_KNOWLEDGE[platform]
    content_type_context = _CONTENT_TYPE_CONTEXT[content_type]

    system_prompt = _SYSTEM.format(
        platform_knowledge=platform_knowledge,
        content_type_context=content_type_context,
        platform=platform,
    )

    user_msg = _USER_TEMPLATE.format(
        platform=platform,
        content_type=content_type,
        text=text[:2000],
    )

    raw = call_claude(
        messages=[{"role": "user", "content": user_msg}],
        max_tokens=1000,
        system=system_prompt,
        context=f"platform optimizer ({platform})",
    )

    parsed = _parse_response(raw)

    if parsed is None:
        fallback = dict(_FALLBACK_TEMPLATE)
        fallback["platform"] = platform
        fallback["hooks_analysis"] = dict(_FALLBACK_TEMPLATE["hooks_analysis"])
        return fallback

    # Ensure all required fields
    parsed.setdefault("platform", platform)
    parsed.setdefault("algorithm_score", 5.0)
    parsed.setdefault("optimizations", [])
    parsed.setdefault("hashtag_suggestions", [])
    parsed.setdefault("posting_time_suggestion", "")
    parsed.setdefault("predicted_engagement_tier", "medium")
    parsed.setdefault("hooks_analysis", {
        "has_hook": False,
        "hook_strength": "none",
        "suggestion": "",
    })

    # Clamp score
    try:
        parsed["algorithm_score"] = max(0.0, min(10.0, float(parsed["algorithm_score"])))
    except (TypeError, ValueError):
        parsed["algorithm_score"] = 5.0

    # Validate engagement tier
    valid_tiers = ("viral", "high", "medium", "low")
    if parsed["predicted_engagement_tier"] not in valid_tiers:
        parsed["predicted_engagement_tier"] = "medium"

    # Validate hooks_analysis structure
    hooks = parsed["hooks_analysis"]
    if not isinstance(hooks, dict):
        parsed["hooks_analysis"] = {
            "has_hook": False,
            "hook_strength": "none",
            "suggestion": "",
        }
    else:
        hooks.setdefault("has_hook", False)
        hooks.setdefault("hook_strength", "none")
        hooks.setdefault("suggestion", "")

    return parsed
