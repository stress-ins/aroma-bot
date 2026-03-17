"""Tests for bot.agents.video_coach — Video Coach Agent."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from bot.agents.video_coach import review_scenario_sync, _parse_response


# --- Helpers ----------------------------------------------------------------

SAMPLE_SCENARIO = """\
ХРОНОМЕТРАЖ: 0-3 сек | Хук
- Видеоряд: макро — рука берёт тёмный флакон с полки
- Текст на экране: Одно масло вместо аптечки
- Закадровый голос: Знаешь, что одно масло может заменить полаптечки?

ХРОНОМЕТРАЖ: 3-10 сек | Основная часть
- Видеоряд: средний план — капля масла на ладонь, растирание
- Текст на экране: Лаванда — от головной боли до сна
- Закадровый голос: Лаванда. Головная боль, бессонница, тревога — всё одним маслом.

ХРОНОМЕТРАЖ: 10-20 сек | Развитие
- Видеоряд: крупный план — диффузор работает, мягкий свет
- Текст на экране: 3 капли перед сном
- Закадровый голос: Три капли в диффузор перед сном — и засыпаешь быстрее.

ХРОНОМЕТРАЖ: 20-30 сек | CTA
- Видеоряд: общий план — уютная спальня, свечи
- Текст на экране: Сохрани, чтобы не забыть
- Закадровый голос: Сохрани себе и попробуй сегодня вечером.
"""

SAMPLE_CLAUDE_RESPONSE = {
    "hook_score": 8.5,
    "retention_prediction": "high",
    "timing_notes": [
        {"frame": 1, "duration_suggestion": 3.0, "note": "Good hook timing"},
        {"frame": 2, "duration_suggestion": 7.0, "note": "Core info, well paced"},
        {"frame": 3, "duration_suggestion": 10.0, "note": "Practical demo holds attention"},
        {"frame": 4, "duration_suggestion": 10.0, "note": "CTA could be shorter, 5-7s enough"},
    ],
    "transition_suggestions": [
        {"from_frame": 1, "to_frame": 2, "type": "cut"},
        {"from_frame": 2, "to_frame": 3, "type": "dissolve"},
        {"from_frame": 3, "to_frame": 4, "type": "zoom"},
    ],
    "sound_cues": [
        {"timestamp": 0.0, "type": "whoosh", "description": "Subtle whoosh on hook text appear"},
        {"timestamp": 10.0, "type": "ambient", "description": "Soft ambient pad for diffuser scene"},
    ],
    "improvements": [
        "Shorten CTA segment to 5-7 seconds for better retention",
        "Add a pattern interrupt at 15 seconds to prevent drop-off",
    ],
    "overall_score": 8.0,
}


# --- Tests ------------------------------------------------------------------

@patch("bot.services.claude_client.call_claude")
def test_review_scenario_basic(mock_call_claude):
    """Review returns valid structure with expected fields."""
    mock_call_claude.return_value = json.dumps(SAMPLE_CLAUDE_RESPONSE)

    result = review_scenario_sync(SAMPLE_SCENARIO)

    assert isinstance(result["hook_score"], float)
    assert 0.0 <= result["hook_score"] <= 10.0
    assert result["retention_prediction"] in ("high", "medium", "low")
    assert isinstance(result["timing_notes"], list)
    assert isinstance(result["transition_suggestions"], list)
    assert isinstance(result["sound_cues"], list)
    assert isinstance(result["improvements"], list)
    assert isinstance(result["overall_score"], float)
    assert 0.0 <= result["overall_score"] <= 10.0


@patch("bot.services.claude_client.call_claude")
def test_review_scenario_with_storyboard(mock_call_claude):
    """Review works when storyboard frames are provided."""
    mock_call_claude.return_value = json.dumps(SAMPLE_CLAUDE_RESPONSE)

    storyboard = [
        {"timecode": "0-3 сек", "scene": "макро — рука берёт флакон"},
        {"timecode": "3-10 сек", "scene": "средний план — капля на ладонь"},
    ]

    result = review_scenario_sync(
        SAMPLE_SCENARIO,
        storyboard=storyboard,
        target_duration=30.0,
    )

    assert result["hook_score"] == 8.5
    assert result["overall_score"] == 8.0
    # Verify storyboard was included in the call
    call_args = mock_call_claude.call_args
    user_content = call_args[1]["messages"][0]["content"]
    assert "STORYBOARD:" in user_content
    assert "Frame 1" in user_content


@patch("bot.services.claude_client.call_claude")
def test_review_scenario_fallback_on_bad_json(mock_call_claude):
    """Returns safe fallback when Claude returns invalid JSON."""
    mock_call_claude.return_value = "This is not valid JSON at all"

    result = review_scenario_sync(SAMPLE_SCENARIO)

    assert result["hook_score"] == 5.0
    assert result["retention_prediction"] == "medium"
    assert result["overall_score"] == 5.0
    assert result["timing_notes"] == []


@patch("bot.services.claude_client.call_claude")
def test_review_scenario_clamps_scores(mock_call_claude):
    """Scores are clamped to 0-10 range."""
    response = dict(SAMPLE_CLAUDE_RESPONSE)
    response["hook_score"] = 15.0
    response["overall_score"] = -3.0
    mock_call_claude.return_value = json.dumps(response)

    result = review_scenario_sync(SAMPLE_SCENARIO)

    assert result["hook_score"] == 10.0
    assert result["overall_score"] == 0.0


@patch("bot.services.claude_client.call_claude")
def test_review_scenario_normalizes_retention(mock_call_claude):
    """Invalid retention_prediction is normalized to 'medium'."""
    response = dict(SAMPLE_CLAUDE_RESPONSE)
    response["retention_prediction"] = "super_high"
    mock_call_claude.return_value = json.dumps(response)

    result = review_scenario_sync(SAMPLE_SCENARIO)

    assert result["retention_prediction"] == "medium"


def test_parse_response_handles_markdown_fence():
    """_parse_response strips markdown code fences."""
    raw = '```json\n{"hook_score": 7, "overall_score": 8}\n```'
    parsed = _parse_response(raw)
    assert parsed is not None
    assert parsed["hook_score"] == 7


def test_parse_response_handles_invalid_json():
    """_parse_response returns None on invalid JSON."""
    assert _parse_response("not json") is None
