"""Video Coach Agent — production guidance for reels scenarios."""
from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)

_SYSTEM = """\
You are an expert Video Coach specializing in short-form vertical video (Reels, TikTok, Shorts).

Your task: review a reels scenario and provide detailed production guidance to maximize \
viewer retention and engagement.

Evaluate the scenario on these dimensions:

1. HOOK EFFECTIVENESS (first 3 seconds)
   - Does the opening grab attention immediately?
   - Is there a visual or verbal hook?
   - Rate 0-10

2. PACING
   - Is each frame/segment held the right duration?
   - Does the video feel rushed or too slow?
   - Provide per-frame timing suggestions

3. TRANSITIONS
   - What transition types work best between frames? (cut, dissolve, zoom, whip pan, match cut)
   - Where are transition opportunities?

4. SOUND DESIGN
   - When to add sound effects (whoosh, ambient, emphasis, ding)
   - Music tempo suggestions
   - Voice-over pacing notes

5. TEXT OVERLAY TIMING
   - When to show/hide overlay text for maximum readability
   - Duration suggestions per text element

6. CALL-TO-ACTION PLACEMENT
   - Where to place CTA for best engagement
   - What type of CTA fits the content

7. RETENTION PATTERNS
   - Does the video maintain interest throughout?
   - Are there dead spots that need energy?
   - Predict retention: "high", "medium", or "low"

TARGET DURATION: {target_duration} seconds

OUTPUT FORMAT — return ONLY valid JSON (no markdown fences, no extra text):
{{
  "hook_score": 0-10,
  "retention_prediction": "high" | "medium" | "low",
  "timing_notes": [
    {{"frame": 1, "duration_suggestion": 3.0, "note": "explanation"}}
  ],
  "transition_suggestions": [
    {{"from_frame": 1, "to_frame": 2, "type": "cut|dissolve|zoom|whip_pan|match_cut"}}
  ],
  "sound_cues": [
    {{"timestamp": 0.0, "type": "whoosh|ambient|emphasis|ding|music_drop", "description": "what and why"}}
  ],
  "improvements": ["actionable suggestion 1", "actionable suggestion 2"],
  "overall_score": 0-10
}}
"""

_USER_TEMPLATE = """\
Review this reels scenario and provide production guidance.

SCENARIO:
{scenario_text}

{storyboard_block}
Provide your production review now. Return ONLY valid JSON."""


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
        logger.warning("Video Coach: failed to parse JSON: %s", text[:300])
        return None


_FALLBACK: dict = {
    "hook_score": 5.0,
    "retention_prediction": "medium",
    "timing_notes": [],
    "transition_suggestions": [],
    "sound_cues": [],
    "improvements": [],
    "overall_score": 5.0,
}


def review_scenario_sync(
    scenario_text: str,
    storyboard: list[dict] | None = None,
    target_duration: float = 30.0,
) -> dict:
    """Review a reels scenario and provide production guidance.

    Returns {
        "hook_score": float,  # 0-10, how strong is the first 3 seconds
        "retention_prediction": str,  # "high" | "medium" | "low"
        "timing_notes": [{"frame": int, "duration_suggestion": float, "note": str}],
        "transition_suggestions": [{"from_frame": int, "to_frame": int, "type": str}],
        "sound_cues": [{"timestamp": float, "type": str, "description": str}],
        "improvements": [str],
        "overall_score": float  # 0-10
    }
    """
    from bot.services.claude_client import call_claude

    system_prompt = _SYSTEM.format(target_duration=target_duration)

    storyboard_block = ""
    if storyboard:
        storyboard_lines = []
        for i, frame in enumerate(storyboard, 1):
            storyboard_lines.append(
                f"Frame {i}: timecode={frame.get('timecode', '?')}, "
                f"scene={frame.get('scene', '?')}"
            )
        storyboard_block = "STORYBOARD:\n" + "\n".join(storyboard_lines)

    user_msg = _USER_TEMPLATE.format(
        scenario_text=str(scenario_text)[:3000],
        storyboard_block=storyboard_block,
    )

    raw = call_claude(
        messages=[{"role": "user", "content": user_msg}],
        max_tokens=1200,
        system=system_prompt,
        context="video coach",
    )

    parsed = _parse_response(raw)

    if parsed is None:
        return dict(_FALLBACK)

    # Ensure all required fields
    parsed.setdefault("hook_score", 5.0)
    parsed.setdefault("retention_prediction", "medium")
    parsed.setdefault("timing_notes", [])
    parsed.setdefault("transition_suggestions", [])
    parsed.setdefault("sound_cues", [])
    parsed.setdefault("improvements", [])
    parsed.setdefault("overall_score", 5.0)

    # Clamp scores to 0-10
    for key in ("hook_score", "overall_score"):
        try:
            parsed[key] = max(0.0, min(10.0, float(parsed[key])))
        except (TypeError, ValueError):
            parsed[key] = 5.0

    # Validate retention_prediction
    if parsed["retention_prediction"] not in ("high", "medium", "low"):
        parsed["retention_prediction"] = "medium"

    return parsed
