"""Tests for carousel text wrapping and text zone detection."""
from __future__ import annotations

import pytest


class TestWrapSlideText:
    def test_short_text_single_line(self):
        from bot.handlers.carousel.generation import wrap_slide_text
        lines = wrap_slide_text("Hello world", max_chars_per_line=30)
        assert lines == ["Hello world"]

    def test_long_text_wraps(self):
        from bot.handlers.carousel.generation import wrap_slide_text
        text = "This is a long sentence that should be wrapped into multiple lines"
        lines = wrap_slide_text(text, max_chars_per_line=28)
        assert len(lines) > 1
        for line in lines:
            # Each line should be at most max_chars + one word overshoot
            assert len(line) <= 40

    def test_consistent_between_preview_and_pptx(self):
        from bot.handlers.carousel.generation import wrap_slide_text
        text = "Утренний ритуал с маслами помогает перезагрузить нервную систему"
        preview_lines = wrap_slide_text(text, max_chars_per_line=28)
        pptx_lines = wrap_slide_text(text, max_chars_per_line=32)
        # Both should produce multiple lines
        assert len(preview_lines) >= 2
        assert len(pptx_lines) >= 2
        # All text preserved
        assert " ".join(preview_lines) == text
        assert " ".join(pptx_lines) == text

    def test_empty_text(self):
        from bot.handlers.carousel.generation import wrap_slide_text
        lines = wrap_slide_text("", max_chars_per_line=30)
        assert lines == []

    def test_single_long_word(self):
        from bot.handlers.carousel.generation import wrap_slide_text
        lines = wrap_slide_text("superlongwordwithoutspaces", max_chars_per_line=10)
        assert lines == ["superlongwordwithoutspaces"]


class TestFindTextZone:
    def test_returns_valid_fractions(self):
        """_find_text_zone should return fractions in valid range."""
        from bot.handlers.carousel.generation import _find_text_zone
        # Create a simple 90x90 grey image
        from PIL import Image
        import io
        img = Image.new("L", (90, 90), 128)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        top_frac, h_frac = _find_text_zone(buf.getvalue())
        assert 0.0 <= top_frac <= 1.0
        assert 0.0 <= h_frac <= 1.0
        assert top_frac + h_frac <= 1.0

    def test_prefers_dark_quiet_zone(self):
        """Dark uniform area should be chosen over bright noisy area."""
        from bot.handlers.carousel.generation import _find_text_zone
        from PIL import Image, ImageDraw
        import io
        import random

        # Create image: top half is noisy+bright, bottom half is dark+uniform
        img = Image.new("L", (90, 90), 20)  # dark base
        draw = ImageDraw.Draw(img)
        # Make top half bright and noisy
        random.seed(42)
        for x in range(90):
            for y in range(45):
                draw.point((x, y), fill=random.randint(180, 255))

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        top_frac, _ = _find_text_zone(buf.getvalue())
        # Should prefer bottom half (top_frac > 0.4)
        assert top_frac > 0.4

    def test_fallback_on_error(self):
        """Invalid image bytes should return safe default."""
        from bot.handlers.carousel.generation import _find_text_zone
        top_frac, h_frac = _find_text_zone(b"not an image")
        assert top_frac == 0.63
        assert h_frac == 0.32
