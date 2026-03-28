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


def test_draft_text_caption_fallback():
    payload = {"caption": "Caption text here"}
    assert _draft_text(payload, "instagram") == "Caption text here"


def test_draft_text_structured_fields():
    payload = {"hook": "Открытие", "angle": "Польза масла", "cta": "Попробуйте сегодня"}
    assert _draft_text(payload, "threads") == "Открытие\n\nПольза масла\n\nПопробуйте сегодня"


def test_draft_text_caption_over_structured():
    """caption should win over hook/angle/cta."""
    payload = {"caption": "Main text", "hook": "Hook", "angle": "Angle"}
    assert _draft_text(payload, "threads") == "Main text"


def test_draft_text_partial_structured():
    payload = {"hook": "Start here", "cta": "Do this"}
    assert _draft_text(payload, "instagram") == "Start here\n\nDo this"


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

    with patch("bot.services.publisher.CAROUSEL_ASSETS_DIR", tmp_path):
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
    with patch("bot.services.publisher.CAROUSEL_ASSETS_DIR", tmp_path):
        paths = _resolve_media_paths("threads", draft_id, payload)
    assert len(paths) == 1


# ---------------------------------------------------------------------------
# Routing: Meta Graph API vs telegram
# ---------------------------------------------------------------------------

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


async def test_publish_routes_to_threads(mock_draft):
    """Threads platform should call Meta Graph API publish_to_threads."""
    mock_publish_to_threads = AsyncMock(return_value={"id": "threads_123"})
    with (
        patch("bot.services.publisher.get_draft", return_value=mock_draft),
        patch("bot.services.publisher.update_draft", return_value=mock_draft),
        patch("bot.services.meta_publisher.publish_to_threads", mock_publish_to_threads),
        patch("bot.services.publish_log_store.save_log", new_callable=AsyncMock, return_value=1),
        patch("bot.services.publish_log_store.update_log_status", new_callable=AsyncMock),
    ):
        results = await publish("d001", ["threads"])

    assert "threads" in results
    assert results["threads"]["status"] == "success"
    assert results["threads"]["external_id"] == "threads_123"
    mock_publish_to_threads.assert_called_once()


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


async def test_publish_routes_mixed(mock_draft):
    """Both Meta Graph API and telegram targets in one call."""
    mock_bot = AsyncMock()
    mock_bot.send_message.return_value = MagicMock(message_id=99)
    mock_publish_to_threads = AsyncMock(return_value={"id": "threads_456"})

    with (
        patch("bot.services.meta_publisher.publish_to_threads", mock_publish_to_threads),
        patch("bot.services.publish_log_store.save_log", new_callable=AsyncMock, return_value=1),
        patch("bot.services.publish_log_store.update_log_status", new_callable=AsyncMock),
        patch("bot.services.telegram_publisher.get_draft", return_value=mock_draft),
        patch("bot.services.telegram_publisher.save_log", return_value=1),
        patch("bot.services.telegram_publisher.update_log_status"),
        patch("bot.services.telegram_publisher.mark_published", new_callable=AsyncMock),
        patch("bot.services.telegram_publisher.mark_failed", new_callable=AsyncMock),
        patch("bot.services.publisher.get_draft", return_value=mock_draft),
        patch("bot.services.publisher.update_draft", return_value=mock_draft),
    ):
        results = await publish(
            "d001", ["threads", "telegram"],
            telegram_bot=mock_bot, telegram_chat_id="123",
        )

    assert "threads" in results
    assert "telegram" in results
    mock_publish_to_threads.assert_called_once()
    mock_bot.send_message.assert_called_once()


async def test_publish_with_photos(tmp_path):
    """Carousel draft with images should publish via Meta Graph API."""
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

    mock_publish_to_instagram = AsyncMock(return_value={"id": "ig_123"})

    with (
        patch("bot.services.publisher.get_draft", return_value=draft),
        patch("bot.services.publisher.update_draft", return_value=draft),
        patch("bot.services.publisher._resolve_media_paths", return_value=[tmp_path / draft_id / "s1.png"]),
        patch("bot.services.meta_publisher.publish_to_instagram", mock_publish_to_instagram),
        patch("bot.services.meta_publisher._get_carousel_image_urls", return_value=["https://example.com/s1.png"]),
        patch("bot.services.publish_log_store.save_log", new_callable=AsyncMock, return_value=1),
        patch("bot.services.publish_log_store.update_log_status", new_callable=AsyncMock),
    ):
        results = await publish(draft_id, ["instagram"])

    assert results["instagram"]["status"] == "success"
    assert results["instagram"]["external_id"] == "ig_123"
    mock_publish_to_instagram.assert_called_once()


async def test_publish_with_schedule(mock_draft):
    """Scheduled publish should mark draft as scheduled."""
    scheduled = datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc)
    mock_publish_to_threads = AsyncMock(return_value={"id": "threads_789"})

    with (
        patch("bot.services.meta_publisher.publish_to_threads", mock_publish_to_threads),
        patch("bot.services.publish_log_store.save_log", new_callable=AsyncMock, return_value=1),
        patch("bot.services.publish_log_store.update_log_status", new_callable=AsyncMock),
        patch("bot.services.publisher.get_draft", return_value=mock_draft),
        patch("bot.services.publisher.update_draft", return_value=mock_draft),
    ):
        results = await publish("d001", ["threads"], scheduled_at=scheduled)

    assert "threads" in results
    assert results["threads"]["status"] == "success"


async def test_publish_threads_no_draft():
    """Publishing to threads with non-existent draft should not crash."""
    with (
        patch("bot.services.publisher.get_draft", return_value=None),
        patch("bot.services.publisher.update_draft", return_value=None),
        patch("bot.services.publish_log_store.save_log", new_callable=AsyncMock, return_value=1),
        patch("bot.services.publish_log_store.update_log_status", new_callable=AsyncMock),
        patch("bot.services.meta_publisher.publish_to_threads", side_effect=RuntimeError("no draft")),
    ):
        results = await publish("nonexistent", ["threads"])
    assert results["threads"]["status"] == "failed"


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


