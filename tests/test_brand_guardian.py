"""Tests for bot.agents.brand_guardian — Brand Guardian Agent."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from bot.agents.brand_guardian import audit_brand_sync, _parse_response


# --- Helpers ----------------------------------------------------------------

def _mock_call_claude_factory(response: dict):
    """Return a mock call_claude that returns the given dict as JSON."""
    def _mock(*, messages, max_tokens, system="", model="claude-haiku-4-5-20251001",
              context="", retries=3):
        return json.dumps(response, ensure_ascii=False)
    return _mock


# --- Tests ------------------------------------------------------------------

@patch("bot.agents.brand_guardian.get_brand_settings_cached")
@patch("bot.services.claude_client.call_claude")
def test_clean_text_passes(mock_call_claude, mock_bs):
    """Clean, on-brand text should pass with a high score."""
    mock_bs.return_value = type("BS", (), {"forbidden_phrases": [], "brand_voice": ""})()
    mock_call_claude.return_value = json.dumps({
        "passed": True,
        "score": 0.95,
        "violations": [],
        "suggested_fixes": [],
        "cleaned_text": "Лаванда традиционно используется для расслабления.",
    })

    result = audit_brand_sync(
        "Лаванда традиционно используется для расслабления.",
        platform="threads",
    )

    assert result["passed"] is True
    assert result["score"] >= 0.8
    assert len(result["violations"]) == 0


@patch("bot.agents.brand_guardian.get_brand_settings_cached")
@patch("bot.services.claude_client.call_claude")
def test_medical_claim_detected(mock_call_claude, mock_bs):
    """Text with medical claims should fail with an error violation."""
    mock_bs.return_value = type("BS", (), {"forbidden_phrases": [], "brand_voice": ""})()
    mock_call_claude.return_value = json.dumps({
        "passed": False,
        "score": 0.3,
        "violations": [
            {
                "type": "medical_claim",
                "detail": "Прямое утверждение лечебного свойства: 'лечит'",
                "severity": "error",
            }
        ],
        "suggested_fixes": [
            "Заменить 'лечит бессонницу' на 'может помочь при бессоннице'"
        ],
        "cleaned_text": "Лаванда может помочь при бессоннице.",
    })

    result = audit_brand_sync(
        "Лаванда лечит бессонницу и исцеляет нервную систему.",
        platform="instagram",
    )

    assert result["passed"] is False
    assert result["score"] < 0.5
    assert any(v["type"] == "medical_claim" for v in result["violations"])
    assert any(v["severity"] == "error" for v in result["violations"])


@patch("bot.agents.brand_guardian.get_brand_settings_cached")
@patch("bot.services.claude_client.call_claude")
def test_ai_stamp_detected(mock_call_claude, mock_bs):
    """Text with AI writing stamps should be flagged."""
    mock_bs.return_value = type("BS", (), {"forbidden_phrases": [], "brand_voice": ""})()
    mock_call_claude.return_value = json.dumps({
        "passed": False,
        "score": 0.6,
        "violations": [
            {
                "type": "ai_stamp",
                "detail": "AI-штамп: 'в мире ароматерапии'",
                "severity": "warning",
            }
        ],
        "suggested_fixes": [
            "Убрать 'в мире ароматерапии', начать с конкретного факта"
        ],
        "cleaned_text": "Эфирные масла цитрусовых поднимают настроение, многие это замечают.",
    })

    result = audit_brand_sync(
        "В мире ароматерапии эфирные масла цитрусовых поистине невероятны.",
        platform="threads",
    )

    assert result["passed"] is False
    assert any(v["type"] == "ai_stamp" for v in result["violations"])
    assert result["cleaned_text"] != ""


@patch("bot.agents.brand_guardian.get_brand_settings_cached")
@patch("bot.services.claude_client.call_claude")
def test_forbidden_phrase_from_brand_settings(mock_call_claude, mock_bs):
    """Forbidden phrases from brand settings DB should be caught."""
    mock_bs.return_value = type("BS", (), {
        "forbidden_phrases": ["тазовая волна", "занимать место без извинений"],
        "brand_voice": "",
    })()
    mock_call_claude.return_value = json.dumps({
        "passed": False,
        "score": 0.5,
        "violations": [
            {
                "type": "forbidden_phrase",
                "detail": "Запрещённая фраза: 'тазовая волна'",
                "severity": "error",
            }
        ],
        "suggested_fixes": ["Убрать 'тазовая волна'"],
        "cleaned_text": "Практика помогает почувствовать тело.",
    })

    result = audit_brand_sync(
        "Тазовая волна помогает почувствовать тело.",
        platform="instagram",
    )

    assert result["passed"] is False
    assert any(v["type"] == "forbidden_phrase" for v in result["violations"])


def test_parse_response_handles_markdown_fence():
    """_parse_response should strip markdown code fences."""
    raw = '```json\n{"passed": true, "score": 0.9, "violations": [], "suggested_fixes": [], "cleaned_text": "ok"}\n```'
    parsed = _parse_response(raw)
    assert parsed["passed"] is True
    assert parsed["score"] == 0.9


def test_parse_response_handles_invalid_json():
    """_parse_response should return a safe fallback on invalid JSON."""
    parsed = _parse_response("this is not json at all")
    assert "passed" in parsed
    assert "score" in parsed
