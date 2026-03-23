"""Tests for stock photo search service and image validation."""

from __future__ import annotations

import asyncio
import io
import json

import httpx
import pytest

from bot.services.stock_photos import (
    StockPhoto,
    _interleave,
    search_stock_photos,
)
from bot.services.image_validation import (
    ValidationResult,
    validate_uploaded_photo,
)


# ---------------------------------------------------------------------------
# Fixtures: mock API responses
# ---------------------------------------------------------------------------

UNSPLASH_RESPONSE = {
    "results": [
        {
            "id": "abc123",
            "width": 4000,
            "height": 5000,
            "alt_description": "lavender field",
            "description": None,
            "urls": {
                "thumb": "https://images.unsplash.com/photo-abc?w=200",
                "regular": "https://images.unsplash.com/photo-abc?w=1080",
                "full": "https://images.unsplash.com/photo-abc",
            },
            "user": {
                "name": "Jane Doe",
                "links": {"html": "https://unsplash.com/@janedoe"},
            },
        },
        {
            "id": "def456",
            "width": 3000,
            "height": 4000,
            "alt_description": "essential oils on table",
            "description": None,
            "urls": {
                "thumb": "https://images.unsplash.com/photo-def?w=200",
                "regular": "https://images.unsplash.com/photo-def?w=1080",
                "full": "https://images.unsplash.com/photo-def",
            },
            "user": {
                "name": "John Smith",
                "links": {"html": "https://unsplash.com/@johnsmith"},
            },
        },
    ]
}

PEXELS_RESPONSE = {
    "photos": [
        {
            "id": 789,
            "width": 3500,
            "height": 4500,
            "photographer": "Alice B",
            "photographer_url": "https://pexels.com/@alice",
            "alt": "spa setting",
            "src": {
                "small": "https://images.pexels.com/789?w=300",
                "large": "https://images.pexels.com/789?w=1080",
                "original": "https://images.pexels.com/789",
            },
        },
    ]
}


# ---------------------------------------------------------------------------
# Tests: interleave
# ---------------------------------------------------------------------------

class TestInterleave:
    def test_empty_lists(self):
        assert _interleave([]) == []
        assert _interleave([[], []]) == []

    def test_single_source(self):
        photos = [StockPhoto(id="1", source="unsplash", url_thumb="", url_regular="",
                             url_full="", width=100, height=100, photographer="",
                             photographer_url="", attribution="", alt_text="")]
        result = _interleave([photos])
        assert len(result) == 1

    def test_interleaves_two_sources(self):
        a = [StockPhoto(id=f"a{i}", source="unsplash", url_thumb="", url_regular="",
                        url_full="", width=0, height=0, photographer="",
                        photographer_url="", attribution="", alt_text="")
             for i in range(3)]
        b = [StockPhoto(id=f"b{i}", source="pexels", url_thumb="", url_regular="",
                        url_full="", width=0, height=0, photographer="",
                        photographer_url="", attribution="", alt_text="")
             for i in range(3)]
        result = _interleave([a, b], max_total=9)
        # Should alternate: a0, b0, a1, b1, a2, b2
        assert result[0].id == "a0"
        assert result[1].id == "b0"
        assert result[2].id == "a1"
        assert len(result) == 6

    def test_caps_at_max(self):
        a = [StockPhoto(id=f"a{i}", source="unsplash", url_thumb="", url_regular="",
                        url_full="", width=0, height=0, photographer="",
                        photographer_url="", attribution="", alt_text="")
             for i in range(10)]
        result = _interleave([a], max_total=5)
        assert len(result) == 5


# ---------------------------------------------------------------------------
# Tests: search (mocked HTTP)
# ---------------------------------------------------------------------------

class TestSearchStockPhotos:
    @pytest.fixture()
    def mock_client(self):
        """httpx async client with mock transport."""
        def handler(request: httpx.Request) -> httpx.Response:
            if "unsplash.com" in str(request.url):
                return httpx.Response(200, json=UNSPLASH_RESPONSE)
            if "pexels.com" in str(request.url):
                return httpx.Response(200, json=PEXELS_RESPONSE)
            return httpx.Response(404)
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    def test_no_keys_returns_empty(self):
        result = asyncio.get_event_loop().run_until_complete(
            search_stock_photos(["lavender"], unsplash_key="", pexels_key="")
        )
        assert result == []

    def test_no_keywords_returns_empty(self):
        result = asyncio.get_event_loop().run_until_complete(
            search_stock_photos([], unsplash_key="key", pexels_key="key")
        )
        assert result == []

    def test_parses_unsplash_response(self, mock_client):
        result = asyncio.get_event_loop().run_until_complete(
            search_stock_photos(["lavender"], unsplash_key="test-key", pexels_key="",
                                _client=mock_client)
        )
        assert len(result) == 2
        assert result[0].source == "unsplash"
        assert result[0].photographer == "Jane Doe"
        assert "Unsplash" in result[0].attribution

    def test_parses_pexels_response(self, mock_client):
        result = asyncio.get_event_loop().run_until_complete(
            search_stock_photos(["spa"], unsplash_key="", pexels_key="test-key",
                                _client=mock_client)
        )
        assert len(result) == 1
        assert result[0].source == "pexels"
        assert result[0].photographer == "Alice B"

    def test_interleaves_both_sources(self, mock_client):
        result = asyncio.get_event_loop().run_until_complete(
            search_stock_photos(["lavender", "spa"], unsplash_key="u", pexels_key="p",
                                _client=mock_client)
        )
        sources = [p.source for p in result]
        assert "unsplash" in sources
        assert "pexels" in sources
        assert sources[0] == "unsplash"
        assert sources[1] == "pexels"

    def test_graceful_fallback_on_api_error(self):
        """If one API fails, return results from the other."""
        def error_handler(request: httpx.Request) -> httpx.Response:
            if "unsplash.com" in str(request.url):
                return httpx.Response(500)
            if "pexels.com" in str(request.url):
                return httpx.Response(200, json=PEXELS_RESPONSE)
            return httpx.Response(404)

        client = httpx.AsyncClient(transport=httpx.MockTransport(error_handler))
        result = asyncio.get_event_loop().run_until_complete(
            search_stock_photos(["lavender"], unsplash_key="u", pexels_key="p",
                                _client=client)
        )
        assert len(result) == 1
        assert result[0].source == "pexels"


# ---------------------------------------------------------------------------
# Tests: image validation
# ---------------------------------------------------------------------------

def _make_test_image(width: int = 1000, height: int = 1000, fmt: str = "JPEG",
                     color: tuple = (128, 128, 128)) -> bytes:
    """Create a test image in memory."""
    from PIL import Image
    img = Image.new("RGB", (width, height), color)
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


class TestImageValidation:
    def test_valid_jpeg(self):
        result = validate_uploaded_photo(_make_test_image())
        assert result.ok is True
        assert result.errors == []
        assert result.width == 1000
        assert result.height == 1000
        assert result.format == "JPEG"

    def test_valid_png(self):
        result = validate_uploaded_photo(_make_test_image(fmt="PNG"))
        assert result.ok is True
        assert result.format == "PNG"

    def test_valid_webp(self):
        result = validate_uploaded_photo(_make_test_image(fmt="WEBP"))
        assert result.ok is True
        assert result.format == "WEBP"

    def test_too_large(self):
        # 11 MB of data
        result = validate_uploaded_photo(b"\x00" * (11 * 1024 * 1024))
        assert result.ok is False
        assert any("большой" in e for e in result.errors)

    def test_invalid_format(self):
        result = validate_uploaded_photo(b"not an image at all")
        assert result.ok is False
        assert any("открыть" in e for e in result.errors)

    def test_too_small_resolution(self):
        result = validate_uploaded_photo(_make_test_image(width=400, height=400))
        assert result.ok is False
        assert any("Разрешение" in e for e in result.errors)

    def test_extreme_aspect_ratio_warns(self):
        result = validate_uploaded_photo(_make_test_image(width=4000, height=1000))
        assert result.ok is True  # not an error, just a warning
        assert any("соотношение" in w for w in result.warnings)

    def test_dark_image_warns(self):
        result = validate_uploaded_photo(_make_test_image(color=(10, 10, 10)))
        assert any("тёмное" in w for w in result.warnings)

    def test_bright_image_warns(self):
        result = validate_uploaded_photo(_make_test_image(color=(240, 240, 240)))
        assert any("светлое" in w for w in result.warnings)

    def test_to_dict(self):
        result = validate_uploaded_photo(_make_test_image())
        d = result.to_dict()
        assert "ok" in d
        assert "errors" in d
        assert "warnings" in d
        assert "width" in d
