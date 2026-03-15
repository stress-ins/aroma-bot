"""Tests for publisher service — routing, media resolution, and publish_log_store."""
from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.services.publisher import (
    _draft_text,
    _resolve_media_paths,
    publish,
    UPLOAD_POST_PLATFORMS,
)
from bot.services.publish_log_store import save_log, list_logs, update_log_status, list_all_logs


# ---------------------------------------------------------------------------
# _draft_text
# ---------------------------------------------------------------------------

def test_draft_text_threads():
    payload = {"text": "Hello Threads!"}
    assert _draft_text(payload, "threads") == "Hello Threads!"


def test_draft_text_carousel():
    payload = {"slides": ["Slide 1", "Slide 2", "Slide 3"]}
    assert _draft_text(payload, "carousel") == "Slide 1\n\nSlide 2\n\nSlide 3"


def test_draft_text_fallback_post():
    payload = {"post": "Post content"}
    assert _draft_text(payload, "instagram") == "Post content"


def test_draft_text_empty():
    assert _draft_text({}, "threads") == ""


# ---------------------------------------------------------------------------
# _resolve_media_paths
# ---------------------------------------------------------------------------

def test_resolve_media_paths_carousel(tmp_path):
    draft_id = "abc123"
    asset_dir = tmp_path / draft_id
    asset_dir.mkdir()
    (asset_dir / "slide_1_aaa.png").write_bytes(b"img1")
    (asset_dir / "slide_2_bbb.png").write_bytes(b"img2")

    payload = {
        "slide_images": [
            {"filename": "slide_1_aaa.png"},
            {"filename": "slide_2_bbb.png"},
            None,
        ]
    }

    with patch("bot.services.upload_post_publisher.CAROUSEL_ASSETS_DIR", tmp_path):
        paths = _resolve_media_paths("carousel", draft_id, payload)

    assert len(paths) == 2
    assert all(p.exists() for p in paths)


def test_resolve_media_paths_no_media():
    paths = _resolve_media_paths("threads", "xyz", {"text": "no media"})
    assert paths == []


def test_resolve_media_paths_single_image(tmp_path):
    draft_id = "img001"
    asset_dir = tmp_path / draft_id
    asset_dir.mkdir()
    (asset_dir / "cover.png").write_bytes(b"cover")

    payload = {"image": {"filename": "cover.png"}}
    with patch("bot.services.upload_post_publisher.CAROUSEL_ASSETS_DIR", tmp_path):
        paths = _resolve_media_paths("threads", draft_id, payload)
    assert len(paths) == 1


# ---------------------------------------------------------------------------
# Routing: upload-post vs telegram
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_upload_client():
    client = MagicMock()
    client.upload_text.return_value = {"request_id": "req_001"}
    client.upload_photos.return_value = {"request_id": "req_002"}
    return client


@pytest.fixture
def mock_draft():
    """A simple approved draft record."""
    from bot.services.drafts_store import DraftRecord
    return DraftRecord(
        draft_id="d001",
        kind="threads",
        topic="Test topic",
        source="test",
        created_at=datetime.now(timezone.utc).isoformat(),
        status="approved",
        feedback="",
        payload={"text": "Test post content"},
    )


async def test_publish_routes_to_upload_post(mock_upload_client, mock_draft):
    """Threads/instagram platforms should call upload-post SDK."""
    with (
        patch("bot.services.upload_post_publisher.get_draft", return_value=mock_draft),
        patch("bot.services.upload_post_publisher._get_upload_client", return_value=mock_upload_client),
        patch("bot.services.upload_post_publisher.settings") as mock_settings,
        patch("bot.services.upload_post_publisher.save_log", return_value=1),
        patch("bot.services.upload_post_publisher.update_log_status"),
        patch("bot.services.upload_post_publisher.mark_published", new_callable=AsyncMock),
        patch("bot.services.upload_post_publisher.mark_failed", new_callable=AsyncMock),
        patch("bot.services.publisher.get_draft", return_value=mock_draft),
        patch("bot.services.publisher.update_draft", return_value=mock_draft),
    ):
        mock_settings.upload_post_api_key = "test_key"
        mock_settings.upload_post_user = "test_user"
        mock_settings.timezone = "Europe/Moscow"

        results = await publish("d001", ["threads"])

    assert "threads" in results
    assert results["threads"]["status"] == "success"
    mock_upload_client.upload_text.assert_called_once()
    call_kwargs = mock_upload_client.upload_text.call_args
    assert call_kwargs.kwargs.get("platforms") or call_kwargs[1].get("platforms") or "threads" in str(call_kwargs)


async def test_publish_routes_to_telegram(mock_draft):
    """Telegram platform should call bot.send_message."""
    mock_bot = AsyncMock()
    mock_bot.send_message.return_value = MagicMock(message_id=42)

    with (
        patch("bot.services.telegram_publisher.get_draft", return_value=mock_draft),
        patch("bot.services.telegram_publisher.save_log", return_value=1),
        patch("bot.services.telegram_publisher.update_log_status"),
        patch("bot.services.telegram_publisher.mark_published", new_callable=AsyncMock),
        patch("bot.services.telegram_publisher.mark_failed", new_callable=AsyncMock),
        patch("bot.services.publisher.get_draft", return_value=mock_draft),
        patch("bot.services.publisher.update_draft", return_value=mock_draft),
    ):
        results = await publish("d001", ["telegram"], telegram_bot=mock_bot, telegram_chat_id="123")

    assert "telegram" in results
    assert results["telegram"]["status"] == "success"
    assert results["telegram"]["external_id"] == "42"
    mock_bot.send_message.assert_called_once()


async def test_publish_routes_mixed(mock_upload_client, mock_draft):
    """Both upload-post and telegram targets in one call."""
    mock_bot = AsyncMock()
    mock_bot.send_message.return_value = MagicMock(message_id=99)

    with (
        patch("bot.services.upload_post_publisher.get_draft", return_value=mock_draft),
        patch("bot.services.upload_post_publisher._get_upload_client", return_value=mock_upload_client),
        patch("bot.services.upload_post_publisher.settings") as mock_settings,
        patch("bot.services.upload_post_publisher.save_log", return_value=1),
        patch("bot.services.upload_post_publisher.update_log_status"),
        patch("bot.services.upload_post_publisher.mark_published", new_callable=AsyncMock),
        patch("bot.services.upload_post_publisher.mark_failed", new_callable=AsyncMock),
        patch("bot.services.telegram_publisher.get_draft", return_value=mock_draft),
        patch("bot.services.telegram_publisher.save_log", return_value=1),
        patch("bot.services.telegram_publisher.update_log_status"),
        patch("bot.services.telegram_publisher.mark_published", new_callable=AsyncMock),
        patch("bot.services.telegram_publisher.mark_failed", new_callable=AsyncMock),
        patch("bot.services.publisher.get_draft", return_value=mock_draft),
        patch("bot.services.publisher.update_draft", return_value=mock_draft),
    ):
        mock_settings.upload_post_api_key = "test_key"
        mock_settings.upload_post_user = "test_user"
        mock_settings.timezone = "Europe/Moscow"

        results = await publish(
            "d001", ["threads", "telegram"],
            telegram_bot=mock_bot, telegram_chat_id="123",
        )

    assert "threads" in results
    assert "telegram" in results
    mock_upload_client.upload_text.assert_called_once()
    mock_bot.send_message.assert_called_once()


async def test_publish_with_photos(mock_upload_client, tmp_path):
    """Carousel draft with images should call upload_photos."""
    from bot.services.drafts_store import DraftRecord

    draft_id = "car01"
    asset_dir = tmp_path / draft_id
    asset_dir.mkdir()
    (asset_dir / "s1.png").write_bytes(b"img")

    draft = DraftRecord(
        draft_id=draft_id,
        kind="carousel",
        topic="Test carousel",
        source="test",
        created_at=datetime.now(timezone.utc).isoformat(),
        status="approved",
        feedback="",
        payload={
            "slides": ["Slide 1", "Slide 2"],
            "slide_images": [{"filename": "s1.png"}],
        },
    )

    with (
        patch("bot.services.upload_post_publisher.get_draft", return_value=draft),
        patch("bot.services.upload_post_publisher._get_upload_client", return_value=mock_upload_client),
        patch("bot.services.upload_post_publisher.CAROUSEL_ASSETS_DIR", tmp_path),
        patch("bot.services.upload_post_publisher.settings") as mock_settings,
        patch("bot.services.upload_post_publisher.save_log", return_value=1),
        patch("bot.services.upload_post_publisher.update_log_status"),
        patch("bot.services.upload_post_publisher.mark_published", new_callable=AsyncMock),
        patch("bot.services.upload_post_publisher.mark_failed", new_callable=AsyncMock),
        patch("bot.services.publisher.get_draft", return_value=draft),
        patch("bot.services.publisher.update_draft", return_value=draft),
    ):
        mock_settings.upload_post_api_key = "key"
        mock_settings.upload_post_user = "user"
        mock_settings.timezone = "Europe/Moscow"

        results = await publish(draft_id, ["instagram"])

    assert results["instagram"]["status"] == "success"
    mock_upload_client.upload_photos.assert_called_once()


async def test_publish_with_schedule(mock_upload_client, mock_draft):
    """Scheduled publish should pass scheduled_date to SDK."""
    scheduled = datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc)

    with (
        patch("bot.services.upload_post_publisher.get_draft", return_value=mock_draft),
        patch("bot.services.upload_post_publisher._get_upload_client", return_value=mock_upload_client),
        patch("bot.services.upload_post_publisher.settings") as mock_settings,
        patch("bot.services.upload_post_publisher.save_log", return_value=1),
        patch("bot.services.upload_post_publisher.update_log_status"),
        patch("bot.services.upload_post_publisher.mark_published", new_callable=AsyncMock),
        patch("bot.services.upload_post_publisher.mark_failed", new_callable=AsyncMock),
        patch("bot.services.publisher.get_draft", return_value=mock_draft),
        patch("bot.services.publisher.update_draft", return_value=mock_draft),
    ):
        mock_settings.upload_post_api_key = "key"
        mock_settings.upload_post_user = "user"
        mock_settings.timezone = "Europe/Moscow"

        results = await publish("d001", ["threads"], scheduled_at=scheduled)

    call_kwargs = mock_upload_client.upload_text.call_args
    assert "scheduled_date" in (call_kwargs.kwargs or {}) or "scheduled_date" in str(call_kwargs)


async def test_publish_draft_not_found():
    """Should raise ValueError for non-existent draft."""
    with patch("bot.services.upload_post_publisher.get_draft", return_value=None):
        with pytest.raises(ValueError, match="not found"):
            await publish("nonexistent", ["threads"])


# ---------------------------------------------------------------------------
# publish_log_store (unit tests with in-memory DB)
# ---------------------------------------------------------------------------

@pytest.fixture
async def in_memory_db():
    """Set up in-memory SQLite for publish_log_store tests."""
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from db.models import Base

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    with patch("bot.services.publish_log_store.AsyncSessionLocal", session_factory):
        yield session_factory

    await engine.dispose()


async def test_save_and_list_logs(in_memory_db):
    log_id = await save_log("d001", "threads", "publish", "pending")
    assert log_id > 0

    logs = await list_logs("d001")
    assert len(logs) == 1
    assert logs[0]["platform"] == "threads"
    assert logs[0]["status"] == "pending"


async def test_update_log_status(in_memory_db):
    log_id = await save_log("d002", "instagram", "publish", "pending")
    await update_log_status(log_id, "success", external_id="ext_123")

    logs = await list_logs("d002")
    assert logs[0]["status"] == "success"
    assert logs[0]["external_id"] == "ext_123"


async def test_list_all_logs(in_memory_db):
    await save_log("d001", "threads", "publish", "success")
    await save_log("d002", "instagram", "publish", "failed", error_message="timeout")

    all_logs = await list_all_logs(limit=10)
    assert len(all_logs) == 2


# ---------------------------------------------------------------------------
# Platform constants
# ---------------------------------------------------------------------------

def test_upload_post_platforms():
    assert "threads" in UPLOAD_POST_PLATFORMS
    assert "instagram" in UPLOAD_POST_PLATFORMS
    assert "telegram" not in UPLOAD_POST_PLATFORMS
