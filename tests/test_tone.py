"""Tests for Tone Adapter feature."""

from __future__ import annotations

from unittest.mock import patch

import pytest


def test_tone_definitions():
    from bot.agents.prompts.tone_prompts import TONE_DEFINITIONS

    assert len(TONE_DEFINITIONS) == 4
    assert "educational" in TONE_DEFINITIONS
    assert "inspirational" in TONE_DEFINITIONS
    assert "selling" in TONE_DEFINITIONS
    assert "storytelling" in TONE_DEFINITIONS

    for key, tone in TONE_DEFINITIONS.items():
        assert "label" in tone
        assert "instruction" in tone


def test_valid_tones():
    from bot.agents.tone_adapter import VALID_TONES

    assert len(VALID_TONES) == 4
    assert "educational" in VALID_TONES
    assert "storytelling" in VALID_TONES


def test_get_tone_labels():
    from bot.agents.tone_adapter import get_tone_labels

    labels = get_tone_labels()
    assert labels["educational"] == "Образовательный"
    assert labels["inspirational"] == "Вдохновляющий"
    assert labels["selling"] == "Продающий"
    assert labels["storytelling"] == "Сторителлинг"


def test_adapt_tone_prompt():
    from bot.agents.prompts.tone_prompts import adapt_tone_prompt

    result = adapt_tone_prompt(
        text="Лаванда помогает уснуть",
        tone_key="educational",
        topic="Лаванда для сна",
        format_key="instagram",
    )
    assert "Образовательный" in result
    assert "Лаванда помогает уснуть" in result
    assert "тезис" in result.lower() or "объяснение" in result.lower()


def test_adapt_tone_prompt_storytelling():
    from bot.agents.prompts.tone_prompts import adapt_tone_prompt

    result = adapt_tone_prompt(
        text="Эвкалипт при простуде",
        tone_key="storytelling",
        topic="Эвкалипт",
        format_key="telegram",
    )
    assert "Сторителлинг" in result
    assert "Однажды" in result


def test_adapt_tone_sync_educational():
    from bot.agents.tone_adapter import adapt_tone_sync

    adapted_text = "Лаванда (Lavandula angustifolia) обладает седативным действием. Исследования показывают: вдыхание лавандового масла снижает уровень кортизола на 15%. Попробуйте: 2 капли на подушку за 30 минут до сна."

    with patch("bot.services.claude_client.call_claude", return_value=adapted_text), \
         patch("bot.agents.creative_team.edit_post_sync", side_effect=lambda text, *a, **kw: text), \
         patch("bot.agents.quality_evaluator._evaluate_sync", return_value={"passed": True, "overall": 0.85}):
        result = adapt_tone_sync(
            text="Лаванда помогает уснуть. Капните пару капель.",
            tone_key="educational",
            topic="Лаванда для сна",
        )

    assert result["tone"] == "educational"
    assert result["label"] == "Образовательный"
    assert "Лаванда" in result["adapted_text"]
    assert result["quality_score"] is not None


def test_adapt_tone_sync_invalid_tone():
    from bot.agents.tone_adapter import adapt_tone_sync

    with pytest.raises(ValueError, match="Unknown tone"):
        adapt_tone_sync("text", "nonexistent", "topic")


def test_adapt_tone_sync_selling():
    from bot.agents.tone_adapter import adapt_tone_sync

    adapted = "Не можешь уснуть? Лаванда решает это за 30 минут. Напишите в ДМ."

    with patch("bot.services.claude_client.call_claude", return_value=adapted), \
         patch("bot.agents.creative_team.edit_post_sync", side_effect=lambda text, *a, **kw: text), \
         patch("bot.agents.quality_evaluator._evaluate_sync", return_value={"passed": True, "overall": 0.8}):
        result = adapt_tone_sync("Лаванда помогает.", "selling", "Лаванда")

    assert result["tone"] == "selling"
    assert "ДМ" in result["adapted_text"]


def test_adapt_tone_prompt_all_tones():
    """Ensure all 4 tones produce valid prompts."""
    from bot.agents.prompts.tone_prompts import TONE_DEFINITIONS, adapt_tone_prompt

    for tone_key in TONE_DEFINITIONS:
        result = adapt_tone_prompt("Текст", tone_key, "Тема", "instagram")
        assert len(result) > 100
        assert "Текст" in result
