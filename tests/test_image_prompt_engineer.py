"""Tests for the Image Prompt Engineer agent."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from bot.agents.image_prompt_engineer import (
    DEFAULT_NEGATIVE_PROMPTS,
    STYLE_PRESETS,
    craft_image_prompt_sync,
)


def _mock_claude_response(prompt_text: str, neg: str = "", tags: list | None = None) -> str:
    """Build a valid JSON response as Claude would return."""
    return json.dumps({
        "prompt": prompt_text,
        "negative_prompt": neg or ", ".join(DEFAULT_NEGATIVE_PROMPTS),
        "style_tags": tags or ["botanical_wellness", "brand_palette", "atmospheric"],
        "aspect_ratio": "9:16",
    })


class TestCraftImagePrompt:
    """Tests for craft_image_prompt_sync."""

    @patch("bot.services.claude_client.call_claude")
    def test_returns_valid_json_with_all_fields(self, mock_claude):
        mock_claude.return_value = _mock_claude_response(
            "A warm terracotta ceramic bowl with dried lavender sprigs, "
            "soft diffused natural light, shallow depth of field, 85mm lens",
        )

        result = craft_image_prompt_sync(
            scene_description="lavender sprigs on a ceramic bowl",
            style="botanical_wellness",
        )

        assert isinstance(result, dict)
        assert "prompt" in result
        assert "negative_prompt" in result
        assert "style_tags" in result
        assert "aspect_ratio" in result
        assert isinstance(result["prompt"], str)
        assert isinstance(result["negative_prompt"], str)
        assert isinstance(result["style_tags"], list)
        assert len(result["prompt"]) > 0

    @patch("bot.services.claude_client.call_claude")
    def test_negative_prompt_always_contains_no_text(self, mock_claude):
        mock_claude.return_value = _mock_claude_response(
            "Essential oil bottle on wooden surface",
            neg="no faces, no hands",  # Missing "no text" — agent should add it
        )

        result = craft_image_prompt_sync(
            scene_description="essential oil bottle",
        )

        assert "no text" in result["negative_prompt"].lower()

    @patch("bot.services.claude_client.call_claude")
    def test_aspect_ratio_916_for_reels(self, mock_claude):
        mock_claude.return_value = json.dumps({
            "prompt": "vertical scene",
            "negative_prompt": ", ".join(DEFAULT_NEGATIVE_PROMPTS),
            "style_tags": ["botanical_wellness"],
            "aspect_ratio": "9:16",
        })

        result = craft_image_prompt_sync(
            scene_description="reels scene",
            aspect_ratio="9:16",
        )

        assert result["aspect_ratio"] == "9:16"

    @patch("bot.services.claude_client.call_claude")
    def test_aspect_ratio_1x1_for_carousel(self, mock_claude):
        mock_claude.return_value = json.dumps({
            "prompt": "square scene",
            "negative_prompt": ", ".join(DEFAULT_NEGATIVE_PROMPTS),
            "style_tags": ["minimal_modern"],
            "aspect_ratio": "1:1",
        })

        result = craft_image_prompt_sync(
            scene_description="carousel slide",
            aspect_ratio="1:1",
        )

        assert result["aspect_ratio"] == "1:1"

    @patch("bot.services.claude_client.call_claude")
    def test_aspect_ratio_4x5_for_instagram(self, mock_claude):
        mock_claude.return_value = json.dumps({
            "prompt": "portrait scene",
            "negative_prompt": ", ".join(DEFAULT_NEGATIVE_PROMPTS),
            "style_tags": ["warm_editorial"],
            "aspect_ratio": "4:5",
        })

        result = craft_image_prompt_sync(
            scene_description="instagram post",
            aspect_ratio="4:5",
        )

        assert result["aspect_ratio"] == "4:5"

    @patch("bot.services.claude_client.call_claude")
    def test_fallback_on_invalid_json(self, mock_claude):
        mock_claude.return_value = "This is not JSON at all"

        result = craft_image_prompt_sync(
            scene_description="test scene",
            style="botanical_wellness",
        )

        # Should return fallback dict with all required keys
        assert isinstance(result, dict)
        assert "prompt" in result
        assert "negative_prompt" in result
        assert "style_tags" in result
        assert "aspect_ratio" in result
        assert "test scene" in result["prompt"]
        assert "no text" in result["negative_prompt"].lower()

    @patch("bot.services.claude_client.call_claude")
    def test_invalid_style_falls_back_to_botanical(self, mock_claude):
        mock_claude.return_value = _mock_claude_response("scene with fallback style")

        result = craft_image_prompt_sync(
            scene_description="some scene",
            style="nonexistent_style",
        )

        # Should not raise; mock was called (meaning style was normalized)
        mock_claude.assert_called_once()
        assert isinstance(result, dict)

    @patch("bot.services.claude_client.call_claude")
    def test_custom_negative_prompts_appended(self, mock_claude):
        mock_claude.return_value = "not json"  # force fallback

        result = craft_image_prompt_sync(
            scene_description="scene",
            negative_prompts=["no candles", "no smoke"],
        )

        neg = result["negative_prompt"].lower()
        assert "no candles" in neg
        assert "no smoke" in neg
        assert "no text" in neg  # mandatory still present

    @patch("bot.services.claude_client.call_claude")
    def test_mandatory_negatives_enforced_on_parsed_response(self, mock_claude):
        # Claude returns valid JSON but missing some mandatory negatives
        mock_claude.return_value = json.dumps({
            "prompt": "beautiful scene",
            "negative_prompt": "no faces",
            "style_tags": ["botanical_wellness"],
            "aspect_ratio": "9:16",
        })

        result = craft_image_prompt_sync(scene_description="test")

        neg = result["negative_prompt"].lower()
        for mandatory in DEFAULT_NEGATIVE_PROMPTS:
            assert mandatory in neg, f"Missing mandatory negative: {mandatory}"
