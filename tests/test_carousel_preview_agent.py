"""Tests for carousel_preview_agent — Vision-based text placement + PNG rendering."""
from __future__ import annotations

import io
import json
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

from bot.agents import carousel_preview_agent
from bot.agents.carousel_preview_agent import (
    SLIDE_ROLES,
    ROLE_PLACEMENT_PREFS,
    analyze_text_placement,
    analyze_reels_placement,
    render_preview_png,
    generate_slide_preview,
    _REELS_PLACEMENT_FALLBACK,
)

_MOD = "bot.agents.carousel_preview_agent"


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_test_image(w: int = 200, h: int = 200, color: str = "blue") -> bytes:
    """Create a small solid-color PNG for testing."""
    from PIL import Image
    img = Image.new("RGB", (w, h), color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _mock_vision_response(placement: dict) -> MagicMock:
    """Create a mock Anthropic response with JSON placement."""
    resp = MagicMock()
    content = MagicMock()
    content.text = json.dumps(placement)
    resp.content = [content]
    return resp


# ── Tests: analyze_text_placement ──────────────────────────────────────────────

class TestAnalyzeTextPlacement:
    def test_returns_dict_with_required_keys(self):
        img = _make_test_image()
        result = analyze_text_placement(img, 0)

        assert isinstance(result, dict)
        for key in ("top", "left", "width", "height", "text_color", "role", "source"):
            assert key in result, f"Missing key: {key}"
        assert result["source"] == "heuristic"  # Vision API temporarily disabled
        assert result["role"] == "hook"

    def test_heuristic_returns_clamped_values(self):
        """Vision API is temporarily disabled; heuristic values are always 0-1."""
        img = _make_test_image()
        result = analyze_text_placement(img, 1)
        for key in ("top", "left", "width", "height"):
            assert 0.0 <= result[key] <= 1.0

    def test_applies_bias(self):
        img = _make_test_image()
        bias = {"top": -0.1, "left": 0.05}
        result_no_bias = analyze_text_placement(img, 0)
        result_bias = analyze_text_placement(img, 0, bias=bias)
        # Bias should shift values
        assert abs(result_bias["top"] - max(0.0, result_no_bias["top"] - 0.1)) < 0.001
        assert abs(result_bias["left"] - min(1.0, result_no_bias["left"] + 0.05)) < 0.001

    def test_fallback_on_error(self):
        img = _make_test_image()

        with patch("bot.agents.carousel_preview_agent.call_claude", side_effect=Exception("API error")):
            result = analyze_text_placement(img, 0)

        assert result["source"] == "heuristic"
        assert "top" in result
        assert "left" in result
        assert result["role"] == "hook"

    def test_fallback_on_invalid_json(self):
        img = _make_test_image()

        with patch("bot.agents.carousel_preview_agent.call_claude", return_value="not json at all"):
            result = analyze_text_placement(img, 2)

        assert result["source"] == "heuristic"

    def test_role_assignment(self):
        img = _make_test_image()
        for i, role in enumerate(SLIDE_ROLES):
            with patch("bot.agents.carousel_preview_agent.call_claude", side_effect=Exception("skip")):
                result = analyze_text_placement(img, i)
            assert result["role"] == role


# ── Tests: render_preview_png ──────────────────────────────────────────────────

class TestRenderPreviewPng:
    def test_returns_valid_png(self):
        img = _make_test_image(400, 400)
        placement = {"top": 0.6, "left": 0.1, "width": 0.8, "height": 0.25, "text_color": "light"}

        result = render_preview_png(img, "Test text overlay", placement)

        assert isinstance(result, bytes)
        assert result[:4] == b"\x89PNG"

    def test_custom_size(self):
        from PIL import Image
        img = _make_test_image(400, 400)
        placement = {"top": 0.5, "left": 0.1, "width": 0.8, "height": 0.3, "text_color": "dark"}

        result = render_preview_png(img, "Text", placement, size=(540, 540))

        output = Image.open(io.BytesIO(result))
        assert output.size == (540, 540)

    def test_dark_text_color(self):
        img = _make_test_image(400, 400, color="white")
        placement = {"top": 0.5, "left": 0.1, "width": 0.8, "height": 0.3, "text_color": "dark"}

        result = render_preview_png(img, "Dark text", placement)
        assert result[:4] == b"\x89PNG"

    def test_long_text_wraps(self):
        img = _make_test_image(400, 400)
        placement = {"top": 0.5, "left": 0.1, "width": 0.8, "height": 0.4, "text_color": "light"}
        long_text = "This is a very long text that should wrap across multiple lines on the slide preview image"

        result = render_preview_png(img, long_text, placement)
        assert result[:4] == b"\x89PNG"


# ── Tests: generate_slide_preview (async) ──────────────────────────────────────

class TestGenerateSlidePreview:
    @pytest.mark.asyncio
    async def test_saves_placement_in_payload(self):
        img = _make_test_image(200, 200)
        draft = MagicMock()
        draft.draft_id = "test123"
        draft.payload = {
            "slides": ["Slide 1 text", "Slide 2 text"],
            "slide_images": [{"filename": "s1.png"}, {"filename": "s2.png"}],
        }

        placement = {"top": 0.6, "left": 0.1, "width": 0.8, "height": 0.25, "text_color": "light"}

        with (
            patch(f"{_MOD}.get_draft", new_callable=AsyncMock, return_value=draft),
            patch(f"{_MOD}.update_draft", new_callable=AsyncMock) as mock_update,
            patch(f"{_MOD}.load_carousel_slide_images", return_value=[img, img]),
            patch(f"{_MOD}.analyze_text_placement", return_value={**placement, "role": "hook", "source": "vision"}),
            patch(f"{_MOD}.render_preview_png", return_value=b"\x89PNG_test"),
            patch("bot.agents.carousel_export_agent.get_aggregate_bias", return_value={}),
        ):
            result = await generate_slide_preview("test123", 0)

        assert result == b"\x89PNG_test"
        # Verify placement was saved
        call_kwargs = mock_update.call_args
        saved_payload = call_kwargs.kwargs.get("payload") or call_kwargs[1].get("payload")
        assert "placement_data" in saved_payload
        assert "0" in saved_payload["placement_data"]

    @pytest.mark.asyncio
    async def test_raises_on_missing_draft(self):
        with patch(f"{_MOD}.get_draft", new_callable=AsyncMock, return_value=None):
            with pytest.raises(ValueError, match="not found"):
                await generate_slide_preview("nonexistent", 0)

    @pytest.mark.asyncio
    async def test_raises_on_invalid_slide_index(self):
        draft = MagicMock()
        draft.payload = {"slides": ["One"]}

        with patch(f"{_MOD}.get_draft", new_callable=AsyncMock, return_value=draft):
            with pytest.raises(ValueError, match="out of range"):
                await generate_slide_preview("test", 5)


class TestAnalyzeReelsPlacement:
    """Vision API is temporarily disabled — all calls return fallback."""

    def test_returns_fallback(self):
        img = _make_test_image()
        r = analyze_reels_placement(img)
        assert r == _REELS_PLACEMENT_FALLBACK

    def test_returns_fallback_always(self):
        """No API call is made, fallback is always returned."""
        r = analyze_reels_placement(_make_test_image())
        assert r["placement"]["zone"] == "top"
        assert r["typography"]["font_weight"] == 700
