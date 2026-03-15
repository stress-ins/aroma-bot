"""Tests for publish API router, scheduler job, and list_scheduled_drafts_due."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from bot.services.drafts_store import DraftRecord


# ---------------------------------------------------------------------------
# list_scheduled_drafts_due
# ---------------------------------------------------------------------------

async def test_list_scheduled_drafts_due_empty():
    """No drafts due when DB is empty."""
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from db.models import Base
    from bot.services.drafts_store import list_scheduled_drafts_due

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    with patch("bot.services.drafts_store.AsyncSessionLocal", factory):
        result = await list_scheduled_drafts_due()
    assert result == []
    await engine.dispose()


async def test_list_scheduled_drafts_due_finds_due():
    """Finds approved drafts with scheduled_at in the past."""
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from db.models import Base, DraftModel
    from bot.services.drafts_store import list_scheduled_drafts_due

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(timezone.utc)

    async with factory() as session:
        session.add(DraftModel(
            draft_id="due01", kind="threads", topic="Due post", source="test",
            status="scheduled", feedback="", payload={"text": "hello"},
            scheduled_at=now - timedelta(minutes=10),
            publish_platforms=["threads"], external_ids={},
        ))
        session.add(DraftModel(
            draft_id="future01", kind="threads", topic="Future", source="test",
            status="scheduled", feedback="", payload={"text": "later"},
            scheduled_at=now + timedelta(hours=2),
            publish_platforms=["threads"], external_ids={},
        ))
        session.add(DraftModel(
            draft_id="pub01", kind="threads", topic="Published", source="test",
            status="published", feedback="", payload={"text": "done"},
            scheduled_at=now - timedelta(hours=1),
            publish_platforms=["threads"], external_ids={},
        ))
        await session.commit()

    with patch("bot.services.drafts_store.AsyncSessionLocal", factory):
        due = await list_scheduled_drafts_due()

    assert len(due) == 1
    assert due[0].draft_id == "due01"
    await engine.dispose()


# ---------------------------------------------------------------------------
# Scheduler job _check_scheduled_posts
# ---------------------------------------------------------------------------

async def test_check_scheduled_posts_calls_publish():
    """The scheduler job should call publish for each due draft."""
    from scheduler.jobs import _check_scheduled_posts

    due_draft = DraftRecord(
        draft_id="sched01", kind="threads", topic="Scheduled",
        source="test", created_at=datetime.now(timezone.utc).isoformat(),
        status="approved", feedback="",
        payload={"text": "hello"}, publish_platforms=["threads"],
    )

    mock_app = MagicMock()
    mock_publish = AsyncMock()
    mock_update = AsyncMock()
    mock_list = AsyncMock(return_value=[due_draft])

    with (
        patch("bot.services.drafts_store.list_scheduled_drafts_due", mock_list),
        patch("bot.services.publisher.publish", mock_publish),
        patch("bot.services.drafts_store.update_draft", mock_update),
    ):
        # Re-import to pick up the patched modules
        import importlib
        import scheduler.jobs as jobs_module
        importlib.reload(jobs_module)
        await jobs_module._check_scheduled_posts(mock_app)

    mock_publish.assert_called_once_with("sched01", ["threads"])


# ---------------------------------------------------------------------------
# Publish API endpoints
# ---------------------------------------------------------------------------

@pytest.fixture
def publish_app():
    """Minimal FastAPI app with publish router, auth bypassed."""
    from fastapi import FastAPI
    from miniapp.api.routers.publish import router
    from miniapp.api.auth import _require_auth

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[_require_auth] = lambda: None
    return app


def test_publish_requires_platforms(publish_app):
    client = TestClient(publish_app)
    draft = DraftRecord(
        draft_id="d01", kind="threads", topic="test",
        source="t", created_at="2026-01-01T00:00:00",
        status="approved", feedback="", payload={},
    )
    with patch("miniapp.api.routers.publish.get_draft", return_value=draft):
        resp = client.post("/api/drafts/d01/publish", json={"platforms": []})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "platforms_required"


def test_publish_requires_approved_status(publish_app):
    client = TestClient(publish_app)
    draft = DraftRecord(
        draft_id="d02", kind="threads", topic="test",
        source="t", created_at="2026-01-01T00:00:00",
        status="draft", feedback="", payload={},
    )
    with patch("miniapp.api.routers.publish.get_draft", return_value=draft):
        resp = client.post("/api/drafts/d02/publish", json={"platforms": ["threads"]})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "draft_must_be_approved"


def test_publish_invalid_platform(publish_app):
    client = TestClient(publish_app)
    draft = DraftRecord(
        draft_id="d03", kind="threads", topic="test",
        source="t", created_at="2026-01-01T00:00:00",
        status="approved", feedback="", payload={},
    )
    with patch("miniapp.api.routers.publish.get_draft", return_value=draft):
        resp = client.post("/api/drafts/d03/publish", json={"platforms": ["facebook"]})
    assert resp.status_code == 400


def test_publish_success(publish_app):
    client = TestClient(publish_app)
    draft = DraftRecord(
        draft_id="d04", kind="threads", topic="test",
        source="t", created_at="2026-01-01T00:00:00",
        status="approved", feedback="", payload={},
    )
    with (
        patch("miniapp.api.routers.publish.get_draft", return_value=draft),
        patch("miniapp.api.routers.publish.publish", new_callable=AsyncMock, return_value={"threads": {"status": "success"}}),
    ):
        resp = client.post("/api/drafts/d04/publish", json={"platforms": ["threads"]})
    assert resp.status_code == 200
    assert resp.json()["results"]["threads"]["status"] == "success"


def test_publish_with_schedule(publish_app):
    client = TestClient(publish_app)
    draft = DraftRecord(
        draft_id="d06", kind="threads", topic="test",
        source="t", created_at="2026-01-01T00:00:00",
        status="approved", feedback="", payload={},
    )
    with (
        patch("miniapp.api.routers.publish.get_draft", return_value=draft),
        patch("miniapp.api.routers.publish.publish", new_callable=AsyncMock, return_value={"threads": {"status": "success"}}) as mock_pub,
    ):
        resp = client.post("/api/drafts/d06/publish", json={
            "platforms": ["threads"],
            "scheduled_at": "2026-03-15T10:00:00+03:00",
        })
    assert resp.status_code == 200
    mock_pub.assert_called_once()
    call_args = mock_pub.call_args
    assert call_args[1].get("scheduled_at") or call_args.args[2] is not None


def test_publish_status_endpoint(publish_app):
    client = TestClient(publish_app)
    draft = DraftRecord(
        draft_id="d05", kind="threads", topic="test",
        source="t", created_at="2026-01-01T00:00:00",
        status="published", feedback="", payload={},
    )
    with (
        patch("miniapp.api.routers.publish.get_draft", return_value=draft),
        patch("miniapp.api.routers.publish.list_logs", new_callable=AsyncMock, return_value=[]),
        patch("miniapp.api.routers.publish.check_status", new_callable=AsyncMock, return_value={}),
    ):
        resp = client.get("/api/drafts/d05/publish-status")
    assert resp.status_code == 200
    assert "logs" in resp.json()


def test_cancel_schedule_endpoint(publish_app):
    client = TestClient(publish_app)
    draft = DraftRecord(
        draft_id="d07", kind="threads", topic="test",
        source="t", created_at="2026-01-01T00:00:00",
        status="scheduled", feedback="", payload={},
    )
    with (
        patch("miniapp.api.routers.publish.get_draft", return_value=draft),
        patch("miniapp.api.routers.publish.cancel_scheduled", new_callable=AsyncMock, return_value={"threads": {"ok": True}}),
    ):
        resp = client.delete("/api/drafts/d07/publish-schedule")
    assert resp.status_code == 200


def test_cancel_schedule_not_scheduled(publish_app):
    client = TestClient(publish_app)
    draft = DraftRecord(
        draft_id="d08", kind="threads", topic="test",
        source="t", created_at="2026-01-01T00:00:00",
        status="approved", feedback="", payload={},
    )
    with patch("miniapp.api.routers.publish.get_draft", return_value=draft):
        resp = client.delete("/api/drafts/d08/publish-schedule")
    assert resp.status_code == 400


def test_scheduled_posts_endpoint(publish_app):
    client = TestClient(publish_app)
    records = [
        DraftRecord(
            draft_id="s01", kind="threads", topic="Scheduled post",
            source="t", created_at="2026-01-01T00:00:00",
            status="approved", feedback="", payload={},
            scheduled_at="2026-03-15T10:00:00+00:00",
            publish_platforms=["threads"],
        ),
    ]
    with patch("bot.services.drafts_store.list_recent_drafts", new_callable=AsyncMock, return_value=records):
        resp = client.get("/api/publish/scheduled")
    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 1


def test_publish_history_endpoint(publish_app):
    client = TestClient(publish_app)
    with patch("miniapp.api.routers.publish.list_all_logs", new_callable=AsyncMock, return_value=[]):
        resp = client.get("/api/publish/history")
    assert resp.status_code == 200
    assert resp.json()["items"] == []
