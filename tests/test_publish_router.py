"""Tests for the publish API router (miniapp/api/routers/publish.py).

Covers:
  POST /api/drafts/{id}/publish
  GET  /api/drafts/{id}/publish-status
  DELETE /api/drafts/{id}/publish-schedule
  GET  /api/publish/scheduled
  GET  /api/publish/history
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _bypass_auth(monkeypatch):
    monkeypatch.setenv("AROMA_BYPASS_AUTH", "1")
    monkeypatch.setenv("AROMA_ENV", "test")


HEADERS = {
    "X-Telegram-Init-Data": "user=%7B%22id%22%3A12345%7D&auth_date=9999999999&hash=abc",
}


@pytest.fixture()
async def approved_draft(setup_test_db):
    from bot.services.team_store import create_team
    from bot.services.drafts_store import save_draft, update_draft

    team = await create_team("Pub Team", creator_telegram_id=12345)
    draft = await save_draft(
        kind="instagram",
        topic="Test publish",
        source="ai",
        payload={"caption": "Test caption"},
        team_id=team.team_id,
        created_by=12345,
    )
    await update_draft(draft.draft_id, status="approved")
    return team, draft


# ---------------------------------------------------------------------------
# POST /api/drafts/{id}/publish
# ---------------------------------------------------------------------------

class TestPublishDraft:
    async def test_publish_not_found(self):
        from miniapp_server import app
        client = TestClient(app)
        resp = client.post(
            "/api/drafts/nonexistent/publish",
            json={"platforms": ["threads"]},
            headers=HEADERS,
        )
        assert resp.status_code == 404

    async def test_publish_requires_approved_status(self, setup_test_db):
        from bot.services.drafts_store import save_draft
        from bot.services.team_store import create_team
        from miniapp_server import app

        team = await create_team("T", creator_telegram_id=12345)
        draft = await save_draft(
            kind="instagram", topic="t", source="ai", payload={},
            team_id=team.team_id, created_by=12345,
        )
        client = TestClient(app)
        resp = client.post(
            f"/api/drafts/{draft.draft_id}/publish",
            json={"platforms": ["threads"]},
            headers=HEADERS,
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "draft_must_be_approved"

    async def test_publish_requires_platforms(self, approved_draft):
        from miniapp_server import app
        _, draft = approved_draft
        client = TestClient(app)
        resp = client.post(
            f"/api/drafts/{draft.draft_id}/publish",
            json={"platforms": []},
            headers=HEADERS,
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "platforms_required"

    async def test_publish_invalid_platform(self, approved_draft):
        from miniapp_server import app
        _, draft = approved_draft
        client = TestClient(app)
        resp = client.post(
            f"/api/drafts/{draft.draft_id}/publish",
            json={"platforms": ["snapchat"]},
            headers=HEADERS,
        )
        assert resp.status_code == 400
        assert "invalid_platform" in resp.json()["detail"]

    async def test_publish_invalid_scheduled_at(self, approved_draft):
        from miniapp_server import app
        _, draft = approved_draft
        client = TestClient(app)
        resp = client.post(
            f"/api/drafts/{draft.draft_id}/publish",
            json={"platforms": ["threads"], "scheduled_at": "not-a-date"},
            headers=HEADERS,
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "invalid_scheduled_at_format"

    async def test_publish_past_scheduled_at(self, approved_draft):
        from miniapp_server import app
        _, draft = approved_draft
        client = TestClient(app)
        resp = client.post(
            f"/api/drafts/{draft.draft_id}/publish",
            json={"platforms": ["threads"], "scheduled_at": "2020-01-01T00:00:00+00:00"},
            headers=HEADERS,
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "scheduled_at_must_be_in_future"

    @patch("miniapp.api.routers.publish.publish", new_callable=AsyncMock)
    async def test_publish_success(self, mock_pub, approved_draft):
        from miniapp_server import app
        mock_pub.return_value = [{"platform": "threads", "status": "success"}]
        _, draft = approved_draft
        client = TestClient(app)
        resp = client.post(
            f"/api/drafts/{draft.draft_id}/publish",
            json={"platforms": ["threads"]},
            headers=HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["draft_id"] == draft.draft_id
        assert len(data["results"]) == 1

    @patch("miniapp.api.routers.publish.publish", new_callable=AsyncMock)
    async def test_publish_failure_returns_safe_error(self, mock_pub, approved_draft):
        from miniapp_server import app
        mock_pub.side_effect = RuntimeError("Internal secret error with token abc123")
        _, draft = approved_draft
        client = TestClient(app)
        resp = client.post(
            f"/api/drafts/{draft.draft_id}/publish",
            json={"platforms": ["threads"]},
            headers=HEADERS,
        )
        assert resp.status_code == 500
        detail = resp.json()["detail"]
        # Should NOT leak internal error details
        assert "token" not in detail.lower()
        assert "secret" not in detail.lower()


# ---------------------------------------------------------------------------
# GET /api/drafts/{id}/publish-status
# ---------------------------------------------------------------------------

class TestPublishStatus:
    async def test_status_not_found(self):
        from miniapp_server import app
        client = TestClient(app)
        resp = client.get("/api/drafts/nonexistent/publish-status", headers=HEADERS)
        assert resp.status_code == 404

    @patch("miniapp.api.routers.publish.check_status", new_callable=AsyncMock, return_value={})
    @patch("miniapp.api.routers.publish.list_logs", new_callable=AsyncMock, return_value=[])
    async def test_status_returns_logs(self, mock_logs, mock_status, approved_draft):
        from miniapp_server import app
        _, draft = approved_draft
        client = TestClient(app)
        resp = client.get(f"/api/drafts/{draft.draft_id}/publish-status", headers=HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert "logs" in data
        assert "remote_status" in data


# ---------------------------------------------------------------------------
# DELETE /api/drafts/{id}/publish-schedule
# ---------------------------------------------------------------------------

class TestCancelSchedule:
    async def test_cancel_not_found(self):
        from miniapp_server import app
        client = TestClient(app)
        resp = client.delete("/api/drafts/nonexistent/publish-schedule", headers=HEADERS)
        assert resp.status_code == 404

    async def test_cancel_not_scheduled(self, approved_draft):
        from miniapp_server import app
        _, draft = approved_draft
        client = TestClient(app)
        resp = client.delete(f"/api/drafts/{draft.draft_id}/publish-schedule", headers=HEADERS)
        assert resp.status_code == 400
        assert resp.json()["detail"] == "draft_not_scheduled"


# ---------------------------------------------------------------------------
# GET /api/publish/scheduled
# ---------------------------------------------------------------------------

class TestScheduledPosts:
    async def test_scheduled_empty(self, setup_test_db):
        from bot.services.team_store import create_team
        from miniapp_server import app
        await create_team("T", creator_telegram_id=12345)
        client = TestClient(app)
        resp = client.get("/api/publish/scheduled", headers=HEADERS)
        assert resp.status_code == 200
        assert resp.json()["items"] == []


# ---------------------------------------------------------------------------
# GET /api/publish/history
# ---------------------------------------------------------------------------

class TestPublishHistory:
    async def test_history_empty(self, setup_test_db):
        from bot.services.team_store import create_team
        from miniapp_server import app
        await create_team("T", creator_telegram_id=12345)
        client = TestClient(app)
        resp = client.get("/api/publish/history", headers=HEADERS)
        assert resp.status_code == 200
        assert resp.json()["items"] == []
