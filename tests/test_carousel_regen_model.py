"""Tests: carousel regen uses img2img only when a revision note is provided."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.helpers import make_draft_kwargs


def _make_carousel_draft(slide_count: int = 3):
    """Return a mock draft with carousel payload."""
    from db.models import DraftModel

    draft = MagicMock(spec=DraftModel)
    draft.kind = "carousel"
    draft.topic = "Test carousel"
    draft.payload = {
        "img_prompts": [f"prompt_{i}" for i in range(slide_count)],
        "slide_images": [
            {"url": f"/generated/carousel_assets/d1/slide_{i}.png", "generated_at": "2026-01-01"}
            for i in range(slide_count)
        ],
        "slide_image_versions": [
            [{"url": f"/generated/carousel_assets/d1/slide_{i}.png"}]
            for i in range(slide_count)
        ],
        "img_prompt_notes": [""] * slide_count,
    }
    return draft


_MODULE = "bot.services.carousel_assets"


@pytest.mark.asyncio
async def test_regen_without_note_uses_text2img():
    """note=None → always text-to-image (no image_urls passed)."""
    draft = _make_carousel_draft()

    with (
        patch(f"{_MODULE}.get_draft", new_callable=AsyncMock, return_value=draft),
        patch(f"{_MODULE}.update_draft", new_callable=AsyncMock, return_value=draft),
        patch(f"{_MODULE}.generate_gemini_image_sync", return_value=MagicMock(image_bytes=b"fake-png")) as mock_gen,
        patch(f"{_MODULE}.save_carousel_slide_asset", return_value={"url": "/new.png"}),
        patch(f"{_MODULE}.optimize_image_prompt", side_effect=lambda p, **kw: p) if False else
        patch("bot.agents.image_prompt_router.optimize_image_prompt", side_effect=lambda p, **kw: p),
        patch(f"{_MODULE}.settings") as mock_settings,
    ):
        mock_settings.assets_base_url = "https://example.com"

        from bot.services.carousel_assets import regenerate_carousel_slide_asset

        await regenerate_carousel_slide_asset("d1", slide_index=0, note=None)

        # image_urls should be None — text-to-image
        call_kwargs = mock_gen.call_args
        assert call_kwargs.kwargs.get("image_urls") is None or call_kwargs[1].get("image_urls") is None


@pytest.mark.asyncio
async def test_regen_with_note_uses_img2img():
    """note="теплее" → img2img with image_urls."""
    draft = _make_carousel_draft()

    with (
        patch(f"{_MODULE}.get_draft", new_callable=AsyncMock, return_value=draft),
        patch(f"{_MODULE}.update_draft", new_callable=AsyncMock, return_value=draft),
        patch(f"{_MODULE}.generate_gemini_image_sync", return_value=MagicMock(image_bytes=b"fake-png")) as mock_gen,
        patch(f"{_MODULE}.save_carousel_slide_asset", return_value={"url": "/new.png"}),
        patch("bot.agents.image_prompt_router.optimize_image_prompt", side_effect=lambda p, **kw: p),
        patch(f"{_MODULE}.settings") as mock_settings,
    ):
        mock_settings.assets_base_url = "https://example.com"

        from bot.services.carousel_assets import regenerate_carousel_slide_asset

        await regenerate_carousel_slide_asset("d1", slide_index=0, note="теплее")

        call_kwargs = mock_gen.call_args
        image_urls = call_kwargs.kwargs.get("image_urls") or call_kwargs[1].get("image_urls")
        assert image_urls is not None
        assert len(image_urls) == 1
        assert "slide_0.png" in image_urls[0]


@pytest.mark.asyncio
async def test_regenerate_all_always_text2img():
    """regenerate_all never uses img2img."""
    draft = _make_carousel_draft()

    with (
        patch(f"{_MODULE}.get_draft", new_callable=AsyncMock, return_value=draft),
        patch(f"{_MODULE}.update_draft", new_callable=AsyncMock, return_value=draft),
        patch(f"{_MODULE}.generate_gemini_image_sync", return_value=MagicMock(image_bytes=b"fake-png")) as mock_gen,
        patch(f"{_MODULE}.save_carousel_slide_asset", return_value={"url": "/new.png"}),
        patch("bot.agents.image_prompt_router.optimize_image_prompt", side_effect=lambda p, **kw: p),
        patch(f"{_MODULE}.settings") as mock_settings,
    ):
        mock_settings.assets_base_url = "https://example.com"

        from bot.services.carousel_assets import regenerate_all_carousel_slide_assets

        await regenerate_all_carousel_slide_assets("d1")

        # Every call should have image_urls=None
        for call in mock_gen.call_args_list:
            image_urls = call.kwargs.get("image_urls") or call[1].get("image_urls")
            assert image_urls is None
