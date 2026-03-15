"""Tests for bot.services.telegram_publisher."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from db.models import Base
import bot.services.drafts_store as ds_mod
from bot.services.drafts_store import save_draft, update_draft


@pytest_asyncio.fixture()
async def in_memory_db(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(ds_mod, "AsyncSessionLocal", factory)
    import bot.services.publish_log_store as pls_mod
    monkeypatch.setattr(pls_mod, "AsyncSessionLocal", factory)
    yield factory
    await engine.dispose()


async def _seed_draft(status: str = "scheduled") -> str:
    rec = await save_draft(
        kind="threads", topic="test", source="test", payload={"text": "hello world"}
    )
    if status != "draft":
        await update_draft(rec.draft_id, status=status)
    return rec.draft_id


@pytest.mark.asyncio
async def test_publish_item_success(in_memory_db):
    from bot.services import telegram_publisher as tp

    did = await _seed_draft("scheduled")
    mock_bot = AsyncMock()
    mock_msg = MagicMock()
    mock_msg.message_id = 42
    mock_bot.send_message.return_value = mock_msg

    with (
        patch.object(tp, "mark_published", new_callable=AsyncMock) as mock_mark,
        patch.object(tp, "mark_failed", new_callable=AsyncMock),
    ):
        result = await tp.publish_item(did, mock_bot, "channel_123")

    assert result["status"] == "success"
    assert result["external_id"] == "42"
    mock_bot.send_message.assert_called_once_with(chat_id="channel_123", text="hello world")
    mock_mark.assert_called_once()


@pytest.mark.asyncio
async def test_publish_item_error(in_memory_db):
    from bot.services import telegram_publisher as tp

    did = await _seed_draft("scheduled")
    mock_bot = AsyncMock()
    mock_bot.send_message.side_effect = RuntimeError("Network error")

    with (
        patch.object(tp, "mark_published", new_callable=AsyncMock),
        patch.object(tp, "mark_failed", new_callable=AsyncMock) as mock_fail,
    ):
        result = await tp.publish_item(did, mock_bot, "channel_123")

    assert result["status"] == "failed"
    assert "Network error" in result["error"]
    mock_fail.assert_called_once()


@pytest.mark.asyncio
async def test_publish_item_no_bot():
    from bot.services import telegram_publisher as tp

    result = await tp.publish_item("any_id", None, "")
    assert result["status"] == "failed"
    assert "not provided" in result["error"]
