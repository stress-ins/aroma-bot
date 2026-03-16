"""Tests for bot.agents.nanobanana_prompt_expert."""
from __future__ import annotations

from unittest.mock import patch

from bot.agents.nanobanana_prompt_expert import optimize_prompt_for_nanobanana


_LONG_RESPONSE = (
    "A serene vertical portrait composition capturing a warm terracotta bowl "
    "filled with dried lavender sprigs resting on a natural linen surface. "
    "Soft golden hour light filters from the left, creating gentle shadows and "
    "warm highlights across the organic textures. Shallow depth of field with "
    "an 85mm portrait lens aesthetic, the background dissolving into creamy "
    "bokeh of muted sage and earth tones. The color palette draws from warm "
    "terracotta, dusty rose, and natural beige, with subtle amber accents "
    "reflecting the calming mood of aromatherapy rituals. Film aesthetic "
    "reminiscent of Kodak Portra 400 with fine grain and rich midtones. "
    "Generous negative space occupies the bottom third of the frame for text "
    "overlay. Professional editorial photography with high resolution and "
    "sharp detail on the hero subject. Rich saturated tones throughout with "
    "no washed-out areas. Absolutely no text, no watermarks, no human faces, "
    "no visible hands in the frame."
)


class TestOptimizePromptForNanobanana:
    def test_returns_expanded_prompt(self):
        with patch("bot.services.claude_client.call_claude", return_value=_LONG_RESPONSE):
            result = optimize_prompt_for_nanobanana(
                "dried lavender on terracotta, soft light",
                topic="Вечерний ритуал ароматерапии",
                slide_number=0,
                total_slides=6,
            )
        assert len(result.split()) >= 50
        assert isinstance(result, str)

    def test_no_midjourney_flags_in_output(self):
        response_with_flags = _LONG_RESPONSE + " --ar 4:5 --style atmospheric --v 6"
        with patch("bot.services.claude_client.call_claude", return_value=response_with_flags):
            result = optimize_prompt_for_nanobanana(
                "scene with herbs",
                topic="Масла для офиса",
                slide_number=1,
                total_slides=6,
            )
        assert "--ar" not in result
        assert "--style" not in result
        assert "--v" not in result

    def test_user_note_passed_to_claude(self):
        captured: dict[str, str] = {}

        def _capture_call(*, messages, max_tokens, system="", context="", **kw):
            captured["user_msg"] = messages[0]["content"]
            return _LONG_RESPONSE

        with patch("bot.services.claude_client.call_claude", side_effect=_capture_call):
            optimize_prompt_for_nanobanana(
                "herbs on a table",
                topic="Утренний ритуал",
                slide_number=2,
                total_slides=6,
                user_note="make it warmer and more golden",
            )
        assert "make it warmer and more golden" in captured["user_msg"]
        assert "integrate naturally" in captured["user_msg"].lower()

    def test_empty_user_note_not_mentioned(self):
        captured: dict[str, str] = {}

        def _capture_call(*, messages, max_tokens, system="", context="", **kw):
            captured["user_msg"] = messages[0]["content"]
            return _LONG_RESPONSE

        with patch("bot.services.claude_client.call_claude", side_effect=_capture_call):
            optimize_prompt_for_nanobanana(
                "herbs on a table",
                topic="Утренний ритуал",
                slide_number=0,
                total_slides=6,
                user_note="",
            )
        assert "revision note" not in captured["user_msg"].lower()

    def test_context_passed_to_claude(self):
        captured: dict[str, str] = {}

        def _capture_call(*, messages, max_tokens, system="", context="", **kw):
            captured["context"] = context
            return _LONG_RESPONSE

        with patch("bot.services.claude_client.call_claude", side_effect=_capture_call):
            optimize_prompt_for_nanobanana(
                "simple scene",
                topic="Тест",
                slide_number=0,
                total_slides=1,
            )
        assert captured["context"] == "nanobanana_prompt_expert"
