"""Tests for bot.services.image_thumbs."""
from bot.services.image_thumbs import thumb_urls, enrich_image_dict


class TestThumbUrls:
    def test_png_url(self):
        urls = thumb_urls("/generated/carousel_assets/abc/slide_1_de34.png")
        assert urls["thumb_url"] == "/generated/carousel_assets/abc/slide_1_de34_thumb.webp"
        assert urls["lqip_url"] == "/generated/carousel_assets/abc/slide_1_de34_lqip.webp"

    def test_empty(self):
        assert thumb_urls("") == {"thumb_url": "", "lqip_url": ""}

    def test_no_extension(self):
        urls = thumb_urls("/path/to/image")
        assert urls["thumb_url"] == "/path/to/image_thumb.webp"


class TestEnrichImageDict:
    def test_adds_thumb_urls(self):
        img = {"url": "/img/test.png"}
        result = enrich_image_dict(img)
        assert result["thumb_url"] == "/img/test_thumb.webp"
        assert result["lqip_url"] == "/img/test_lqip.webp"

    def test_skips_if_already_present(self):
        img = {"url": "/img/test.png", "thumb_url": "/custom.webp"}
        result = enrich_image_dict(img)
        assert result["thumb_url"] == "/custom.webp"

    def test_none_input(self):
        assert enrich_image_dict(None) is None

    def test_empty_url(self):
        img = {"url": ""}
        result = enrich_image_dict(img)
        assert "thumb_url" not in result
