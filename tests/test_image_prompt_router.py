"""Tests for bot.agents.image_prompt_router."""
from __future__ import annotations

from bot.agents.image_prompt_router import MODEL_PROFILES, optimize_image_prompt


class TestModelProfiles:
    def test_all_required_models_present(self):
        assert "gpt-image/1.5-text-to-image" in MODEL_PROFILES
        assert "google/nano-banana" in MODEL_PROFILES
        assert "google/nano-banana-edit" in MODEL_PROFILES

    def test_each_profile_has_required_keys(self):
        for model, profile in MODEL_PROFILES.items():
            assert "type" in profile, f"{model} missing 'type'"
            assert "system" in profile, f"{model} missing 'system'"
            assert "max_tokens" in profile, f"{model} missing 'max_tokens'"
            assert profile["type"] in ("text-to-image", "img2img"), f"{model} has invalid type"

    def test_gpt_image_is_concise(self):
        profile = MODEL_PROFILES["gpt-image/1.5-text-to-image"]
        assert profile["max_tokens"] <= 400
        assert profile["type"] == "text-to-image"

    def test_nanobanana_is_verbose(self):
        profile = MODEL_PROFILES["google/nano-banana"]
        assert profile["max_tokens"] >= 500
        assert profile["type"] == "text-to-image"

    def test_nanobanana_edit_is_img2img(self):
        profile = MODEL_PROFILES["google/nano-banana-edit"]
        assert profile["type"] == "img2img"


class TestOptimizeImagePrompt:
    def test_calls_claude_with_model_system(self, monkeypatch):
        captured = {}

        def _fake_call_claude(*, messages, max_tokens, system, context, **kw):
            captured["system"] = system
            captured["max_tokens"] = max_tokens
            captured["user_msg"] = messages[0]["content"]
            return "optimized prompt result"

        monkeypatch.setattr("bot.services.claude_client.call_claude", _fake_call_claude)

        result = optimize_image_prompt(
            "a bottle on table", model="gpt-image/1.5-text-to-image",
            topic="morning ritual", slide_number=0, total_slides=5,
        )
        assert result == "optimized prompt result"
        assert captured["max_tokens"] == 300  # gpt-image profile
        assert "morning ritual" in captured["user_msg"]

    def test_blend_mood_injected_into_system(self, monkeypatch):
        captured = {}

        def _fake_call_claude(*, messages, max_tokens, system, context, **kw):
            captured["system"] = system
            return "optimized"

        monkeypatch.setattr("bot.services.claude_client.call_claude", _fake_call_claude)

        optimize_image_prompt(
            "bottle", model="google/nano-banana",
            blend_mood="warm amber palette, rosemary botanicals",
        )
        assert "warm amber palette" in captured["system"]
        assert "PRIMARY visual driver" in captured["system"]

    def test_no_blend_mood_no_block(self, monkeypatch):
        captured = {}

        def _fake_call_claude(*, messages, max_tokens, system, context, **kw):
            captured["system"] = system
            return "optimized"

        monkeypatch.setattr("bot.services.claude_client.call_claude", _fake_call_claude)

        optimize_image_prompt("bottle", model="google/nano-banana")
        assert "PRIMARY visual driver" not in captured["system"]

    def test_unknown_model_uses_default(self, monkeypatch):
        captured = {}

        def _fake_call_claude(*, messages, max_tokens, system, context, **kw):
            captured["max_tokens"] = max_tokens
            return "optimized"

        monkeypatch.setattr("bot.services.claude_client.call_claude", _fake_call_claude)

        optimize_image_prompt("bottle", model="unknown/model")
        assert captured["max_tokens"] == 600  # default = nanobanana profile

    def test_strips_mj_parameters(self, monkeypatch):
        def _fake_call_claude(*, messages, max_tokens, system, context, **kw):
            return "beautiful scene --ar 4:5 --style raw"

        monkeypatch.setattr("bot.services.claude_client.call_claude", _fake_call_claude)

        result = optimize_image_prompt("bottle", model="gpt-image/1.5-text-to-image")
        assert "--ar" not in result
        assert "--style" not in result

    def test_user_note_included(self, monkeypatch):
        captured = {}

        def _fake_call_claude(*, messages, max_tokens, system, context, **kw):
            captured["user_msg"] = messages[0]["content"]
            return "optimized"

        monkeypatch.setattr("bot.services.claude_client.call_claude", _fake_call_claude)

        optimize_image_prompt(
            "bottle", model="gpt-image/1.5-text-to-image",
            user_note="make it warmer",
        )
        assert "make it warmer" in captured["user_msg"]
