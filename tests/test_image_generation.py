"""Tests for image generation script and related service functions (PR 4)."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.generate_missing_images as generator


# ---------------------------------------------------------------------------
# Test 1: SVG placeholder detection
# ---------------------------------------------------------------------------

def test_svg_placeholder_detected():
    """_is_placeholder returns True for SVG data-URI and empty string."""
    assert generator._is_placeholder("data:image/svg+xml;charset=UTF-8,%3Csvg%20...")
    assert generator._is_placeholder("")
    assert generator._is_placeholder(None)
    assert not generator._is_placeholder("/reference-images/aromas/lavender.jpg")
    assert not generator._is_placeholder("https://example.com/img.jpg")


# ---------------------------------------------------------------------------
# Test 2: dry-run returns cards without images
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dry_run_returns_cards_without_images(tmp_path):
    """dry-run lists placeholder cards without generating anything."""
    # Insert a card with no real image
    from db.session import AsyncSessionLocal
    from db.models import AromaCardModel
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        from sqlalchemy import select
        result = await session.execute(
            select(AromaCardModel).where(AromaCardModel.slug == "imgtest-no-image")
        )
        if not result.scalar_one_or_none():
            session.add(AromaCardModel(
                slug="imgtest-no-image",
                name="Тест Без Картинки",
                category="aroma",
                source_type="flower",
                aliases=[],
                payload={"description": "Тестовое масло"},
            ))
            await session.commit()

    # Dry-run should find it and return slug without writing files
    write_calls = []

    async def fake_audit(category):
        return [{"slug": "imgtest-no-image", "name": "Тест Без Картинки",
                 "category": "aroma", "source_type": "flower", "description": ""}]

    with patch.object(generator, "_audit_cards", new=fake_audit):
        result = await generator.run(dry_run=True, category="aroma")

    assert "imgtest-no-image" in result
    # No files should be written during dry-run
    assert not list(tmp_path.glob("**/*.jpg"))


# ---------------------------------------------------------------------------
# Test 3: image saved to correct path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_image_saved_to_correct_path(tmp_path):
    """Generated image is saved to assets/reference_images/{category}s/{slug}.jpg."""
    fake_card = {"slug": "lavender-imgtest", "name": "Лаванда",
                 "category": "aroma", "source_type": "flower", "description": "Тест"}
    fake_bytes = b"\xff\xd8\xff\xe0FAKEJPEG"

    async def fake_audit(category):
        return [fake_card]

    async def fake_upsert(slug, image_url):
        pass

    with (
        patch.object(generator, "_audit_cards", new=fake_audit),
        patch.object(generator, "_generate_image", return_value=fake_bytes),
        patch.object(generator, "_upsert_image_url", new=AsyncMock()),
        patch.object(generator, "IMAGES_DIR", tmp_path / "reference_images"),
        patch("config.settings") as mock_settings,
        patch("time.sleep"),
    ):
        mock_settings.image_api_key = "fake-key"
        result = await generator.run(dry_run=False, category="aroma")

    assert "lavender-imgtest" in result
    expected_path = tmp_path / "reference_images" / "aromas" / "lavender-imgtest.jpg"
    assert expected_path.exists()
    assert expected_path.read_bytes() == fake_bytes


# ---------------------------------------------------------------------------
# Test 4: generation failure does not stop the whole batch
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generation_failure_skips_card(tmp_path):
    """If Gemini fails for one card, the rest are still processed."""
    cards = [
        {"slug": "fail-card", "name": "Проблемная", "category": "aroma", "source_type": "flower", "description": ""},
        {"slug": "ok-card", "name": "Нормальная", "category": "aroma", "source_type": "flower", "description": ""},
    ]
    fake_bytes = b"\xff\xd8FAKEJPEG"

    async def fake_audit(category):
        return cards

    def fake_generate(name, desc, category="aroma"):
        if name == "Проблемная":
            return None  # simulate failure
        return fake_bytes

    with (
        patch.object(generator, "_audit_cards", new=fake_audit),
        patch.object(generator, "_generate_image", side_effect=fake_generate),
        patch.object(generator, "_upsert_image_url", new=AsyncMock()),
        patch.object(generator, "IMAGES_DIR", tmp_path / "reference_images"),
        patch("config.settings") as mock_settings,
        patch("time.sleep"),
    ):
        mock_settings.image_api_key = "fake-key"
        result = await generator.run(dry_run=False, category="aroma")

    # Only the successful card is in result
    assert "ok-card" in result
    assert "fail-card" not in result


# ---------------------------------------------------------------------------
# Test 5: _payload_image_url returns stored URL if file exists
# ---------------------------------------------------------------------------

def test_payload_image_url_returns_stored_if_file_exists(tmp_path):
    """_payload_image_url returns URL when referenced file exists on disk."""
    from bot.services.miniapp_references import _payload_image_url, REFERENCE_IMAGES_DIR

    # Create a fake image file
    fake_dir = tmp_path / "aromas"
    fake_dir.mkdir(parents=True)
    fake_file = fake_dir / "lavender.jpg"
    fake_file.write_bytes(b"FAKEIMG")

    with patch("bot.services.miniapp_references.common.REFERENCE_IMAGES_DIR", tmp_path):
        result = _payload_image_url({"image_url": "/reference-images/aromas/lavender.jpg"})

    assert result == "/reference-images/aromas/lavender.jpg"


def test_payload_image_url_returns_none_if_file_missing(tmp_path):
    """_payload_image_url returns None if referenced file doesn't exist."""
    from bot.services.miniapp_references import _payload_image_url

    with patch("bot.services.miniapp_references.common.REFERENCE_IMAGES_DIR", tmp_path):
        result = _payload_image_url({"image_url": "/reference-images/aromas/missing.jpg"})

    assert result is None


def test_payload_image_url_returns_none_for_svg():
    """_payload_image_url returns None for SVG data-URI (triggers re-generation)."""
    from bot.services.miniapp_references import _payload_image_url

    result = _payload_image_url({"image_url": "data:image/svg+xml;charset=UTF-8,%3Csvg..."})
    assert result is None
