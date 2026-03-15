"""Tests for bot.services.upload_post_publisher."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from db.models import Base
import bot.services.drafts_store as ds_mod
from bot.services.drafts_store import save_draft, get_draft, update_draft


@pytest_asyncio.fixture()
async def in_memory_db(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(ds_mod, "AsyncSessionLocal", factory)
    # Also patch publish_log_store to use same DB
    import bot.services.publish_log_store as pls_mod
    monkeypatch.setattr(pls_mod, "AsyncSessionLocal", factory)
    yield factory
    await engine.dispose()


def _mock_upload_client():
    client = MagicMock()
    client.upload_text.return_value = {"request_id": "req_123"}
    client.upload_photos.return_value = {"request_id": "req_456"}
    client.get_status.return_value = {"status": "completed"}
    client.cancel_scheduled.return_value = {"cancelled": True}
    return client


async def _seed_draft(status: str = "scheduled") -> str:
    rec = await save_draft(
        kind="threads", topic="test", source="test", payload={"text": "hello world"}
    )
    if status != "draft":
        await update_draft(rec.draft_id, status=status)
    return rec.draft_id


@pytest.mark.asyncio
async def test_publish_item_text(in_memory_db):
    from bot.services import upload_post_publisher as upp

    did = await _seed_draft("scheduled")
    mock_client = _mock_upload_client()

    with (
        patch.object(upp, "_get_upload_credentials", new_callable=AsyncMock, return_value=("key", "testuser")),
        patch.object(upp, "_get_upload_client", return_value=mock_client),
        patch.object(upp, "_ensure_user"),
        patch.object(upp, "mark_published", new_callable=AsyncMock) as mock_mark,
        patch.object(upp, "mark_failed", new_callable=AsyncMock),
    ):
        results = await upp.publish_item(did, ["threads"])

    assert results["threads"]["status"] == "success"
    assert results["threads"]["external_id"] == "req_123"
    mock_client.upload_text.assert_called_once()
    mock_mark.assert_called_once()


@pytest.mark.asyncio
async def test_publish_item_error_calls_mark_failed(in_memory_db):
    from bot.services import upload_post_publisher as upp

    did = await _seed_draft("scheduled")
    mock_client = _mock_upload_client()
    mock_client.upload_text.side_effect = RuntimeError("API down")

    with (
        patch.object(upp, "_get_upload_credentials", new_callable=AsyncMock, return_value=("key", "testuser")),
        patch.object(upp, "_get_upload_client", return_value=mock_client),
        patch.object(upp, "_ensure_user"),
        patch.object(upp, "mark_published", new_callable=AsyncMock),
        patch.object(upp, "mark_failed", new_callable=AsyncMock) as mock_fail,
    ):
        results = await upp.publish_item(did, ["threads"])

    assert results["threads"]["status"] == "failed"
    mock_fail.assert_called_once()


@pytest.mark.asyncio
async def test_publish_item_with_schedule(in_memory_db):
    from bot.services import upload_post_publisher as upp

    did = await _seed_draft("scheduled")
    mock_client = _mock_upload_client()
    sched = datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc)

    with (
        patch.object(upp, "_get_upload_credentials", new_callable=AsyncMock, return_value=("key", "testuser")),
        patch.object(upp, "_get_upload_client", return_value=mock_client),
        patch.object(upp, "_ensure_user"),
        patch.object(upp, "mark_published", new_callable=AsyncMock) as mock_mark,
        patch.object(upp, "mark_failed", new_callable=AsyncMock),
        patch("config.settings") as mock_settings,
    ):
        mock_settings.timezone = "UTC"
        results = await upp.publish_item(did, ["instagram"], scheduled_at=sched)

    assert results["instagram"]["status"] == "success"
    # scheduled publish should NOT call mark_published (it stays scheduled)
    mock_mark.assert_not_called()


@pytest.mark.asyncio
async def test_publish_item_not_found(in_memory_db):
    from bot.services import upload_post_publisher as upp

    with pytest.raises(ValueError, match="not found"):
        await upp.publish_item("nonexistent", ["threads"])


@pytest.mark.asyncio
async def test_check_status(in_memory_db):
    from bot.services import upload_post_publisher as upp

    did = await _seed_draft("published")
    await update_draft(did, external_ids={"threads": "ext1"})
    mock_client = _mock_upload_client()

    with patch.object(upp, "_get_upload_client", return_value=mock_client):
        result = await upp.check_status(did)

    assert "threads" in result
    mock_client.get_status.assert_called_once_with(request_id="ext1")
