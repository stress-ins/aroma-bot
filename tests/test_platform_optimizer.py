"""Tests for bot.agents.platform_optimizer — Platform Optimizer Agent."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from bot.agents.platform_optimizer import optimize_for_platform_sync, _parse_response


# --- Helpers ----------------------------------------------------------------

SAMPLE_POST = "Лаванда — это не просто приятный запах. Три капли перед сном, и засыпаешь быстрее."

THREADS_RESPONSE = {
    "platform": "threads",
    "algorithm_score": 7.5,
    "optimizations": [
        {
            "type": "hook",
            "current": "Лаванда — это не просто приятный запах.",
            "suggested": "Ты до сих пор считаешь лаванду просто приятным запахом?",
            "impact": "high",
        },
        {
            "type": "cta",
            "current": "No CTA",
            "suggested": "End with a question to drive replies",
            "impact": "medium",
        },
    ],
    "hashtag_suggestions": [],
    "posting_time_suggestion": "Early morning 7-9 AM or evening 8-10 PM",
    "predicted_engagement_tier": "high",
    "hooks_analysis": {
        "has_hook": True,
        "hook_strength": "moderate",
        "suggestion": "Rephrase as a question for stronger hook",
    },
}

INSTAGRAM_RESPONSE = {
    "platform": "instagram",
    "algorithm_score": 6.0,
    "optimizations": [
        {
            "type": "format",
            "current": "Single text post",
            "suggested": "Convert to carousel for higher engagement",
            "impact": "high",
        },
    ],
    "hashtag_suggestions": ["ароматерапия", "лаванда", "сон", "эфирныемасла", "wellness"],
    "posting_time_suggestion": "Weekdays 11 AM - 1 PM or 7-9 PM",
    "predicted_engagement_tier": "medium",
    "hooks_analysis": {
        "has_hook": True,
        "hook_strength": "moderate",
        "suggestion": "First slide should be bolder",
    },
}

TIKTOK_RESPONSE = {
    "platform": "tiktok",
    "algorithm_score": 5.5,
    "optimizations": [
        {
            "type": "length",
            "current": "Text-based content",
            "suggested": "Adapt for 7-15 second video format",
            "impact": "high",
        },
    ],
    "hashtag_suggestions": ["aromatherapy", "lavender", "sleephack", "wellness"],
    "posting_time_suggestion": "Evenings 7-11 PM, weekends perform best",
    "predicted_engagement_tier": "medium",
    "hooks_analysis": {
        "has_hook": False,
        "hook_strength": "weak",
        "suggestion": "Start with a bold claim or visual hook",
    },
}


# --- Tests ------------------------------------------------------------------

@patch("bot.services.claude_client.call_claude")
def test_optimize_threads(mock_call_claude):
    """Threads optimization returns correct structure and no hashtags."""
    mock_call_claude.return_value = json.dumps(THREADS_RESPONSE)

    result = optimize_for_platform_sync(SAMPLE_POST, platform="threads")

    assert result["platform"] == "threads"
    assert isinstance(result["algorithm_score"], float)
    assert 0.0 <= result["algorithm_score"] <= 10.0
    assert isinstance(result["optimizations"], list)
    assert len(result["optimizations"]) > 0
    assert result["hashtag_suggestions"] == []
    assert result["predicted_engagement_tier"] in ("viral", "high", "medium", "low")


@patch("bot.services.claude_client.call_claude")
def test_optimize_instagram(mock_call_claude):
    """Instagram optimization includes hashtag suggestions."""
    mock_call_claude.return_value = json.dumps(INSTAGRAM_RESPONSE)

    result = optimize_for_platform_sync(SAMPLE_POST, platform="instagram", content_type="post")

    assert result["platform"] == "instagram"
    assert isinstance(result["hashtag_suggestions"], list)
    assert len(result["hashtag_suggestions"]) > 0
    assert result["hooks_analysis"]["has_hook"] is True


@patch("bot.services.claude_client.call_claude")
def test_optimize_tiktok(mock_call_claude):
    """TikTok optimization works and includes hooks analysis."""
    mock_call_claude.return_value = json.dumps(TIKTOK_RESPONSE)

    result = optimize_for_platform_sync(SAMPLE_POST, platform="tiktok", content_type="reels")

    assert result["platform"] == "tiktok"
    assert isinstance(result["hooks_analysis"], dict)
    assert "has_hook" in result["hooks_analysis"]
    assert "hook_strength" in result["hooks_analysis"]
    assert "suggestion" in result["hooks_analysis"]


@patch("bot.services.claude_client.call_claude")
def test_optimize_unknown_platform_defaults_to_instagram(mock_call_claude):
    """Unknown platform falls back to instagram."""
    mock_call_claude.return_value = json.dumps(INSTAGRAM_RESPONSE)

    result = optimize_for_platform_sync(SAMPLE_POST, platform="mastodon")

    # Should not crash; platform normalized internally
    assert result["platform"] == "instagram"


@patch("bot.services.claude_client.call_claude")
def test_optimize_fallback_on_bad_json(mock_call_claude):
    """Returns safe fallback when Claude returns invalid JSON."""
    mock_call_claude.return_value = "broken response"

    result = optimize_for_platform_sync(SAMPLE_POST, platform="instagram")

    assert result["platform"] == "instagram"
    assert result["algorithm_score"] == 5.0
    assert result["predicted_engagement_tier"] == "medium"
    assert result["optimizations"] == []


@patch("bot.services.claude_client.call_claude")
def test_optimize_clamps_score(mock_call_claude):
    """Algorithm score is clamped to 0-10."""
    response = dict(INSTAGRAM_RESPONSE)
    response["algorithm_score"] = 99.0
    mock_call_claude.return_value = json.dumps(response)

    result = optimize_for_platform_sync(SAMPLE_POST, platform="instagram")

    assert result["algorithm_score"] == 10.0


@patch("bot.services.claude_client.call_claude")
def test_optimize_normalizes_engagement_tier(mock_call_claude):
    """Invalid engagement tier is normalized to 'medium'."""
    response = dict(INSTAGRAM_RESPONSE)
    response["predicted_engagement_tier"] = "super_viral"
    mock_call_claude.return_value = json.dumps(response)

    result = optimize_for_platform_sync(SAMPLE_POST, platform="instagram")

    assert result["predicted_engagement_tier"] == "medium"


def test_parse_response_handles_markdown_fence():
    """_parse_response strips markdown code fences."""
    raw = '```json\n{"platform": "threads", "algorithm_score": 7}\n```'
    parsed = _parse_response(raw)
    assert parsed is not None
    assert parsed["algorithm_score"] == 7


def test_parse_response_handles_invalid_json():
    """_parse_response returns None on invalid JSON."""
    assert _parse_response("not json at all") is None
