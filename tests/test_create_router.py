"""Tests for the create API router (miniapp/api/routers/create.py).

Covers validation of content generation endpoints:
  POST /api/suggest-topics
  POST /api/generate/content
  POST /api/generate/carousel
  POST /api/generate/threads-series
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _bypass_auth(monkeypatch):
    monkeypatch.setenv("AROMA_BYPASS_AUTH", "1")
    monkeypatch.setenv("AROMA_ENV", "test")
    from config import settings
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")


HEADERS = {
    "X-Telegram-Init-Data": "user=%7B%22id%22%3A12345%7D&auth_date=9999999999&hash=abc",
}


@pytest.fixture()
async def team_ready(setup_test_db):
    from bot.services.team_store import create_team
    return await create_team("Create Team", creator_telegram_id=12345)


# ---------------------------------------------------------------------------
# POST /api/generate/content — validation
# ---------------------------------------------------------------------------

class TestGenerateContent:
    async def test_empty_topic(self, team_ready):
        from miniapp_server import app
        client = TestClient(app)
        resp = client.post(
            "/api/generate/content",
            json={"topic": "", "goal_key": "trust", "format_key": "instagram"},
            headers=HEADERS,
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "empty_topic"

    async def test_whitespace_only_topic(self, team_ready):
        from miniapp_server import app
        client = TestClient(app)
        resp = client.post(
            "/api/generate/content",
            json={"topic": "   ", "goal_key": "trust", "format_key": "instagram"},
            headers=HEADERS,
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "empty_topic"

    async def test_invalid_goal(self, team_ready):
        from miniapp_server import app
        client = TestClient(app)
        resp = client.post(
            "/api/generate/content",
            json={"topic": "test topic", "goal_key": "nonexistent_goal", "format_key": "instagram"},
            headers=HEADERS,
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "invalid_goal"

    async def test_invalid_format(self, team_ready):
        from miniapp_server import app
        client = TestClient(app)
        resp = client.post(
            "/api/generate/content",
            json={"topic": "test topic", "goal_key": "trust", "format_key": "tiktok"},
            headers=HEADERS,
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "invalid_format"

    async def test_valid_content_creates_stub_draft(self, team_ready):
        """Valid content request creates a stub draft and returns it immediately (generation runs in background)."""
        from miniapp_server import app
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/generate/content",
            json={"topic": "Lavender for sleep", "goal_key": "trust", "format_key": "instagram"},
            headers=HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "draft_id" in data
        assert data["kind"] == "instagram"
        assert data["topic"] == "Lavender for sleep"


# ---------------------------------------------------------------------------
# POST /api/generate/carousel — validation
# ---------------------------------------------------------------------------

class TestGenerateCarousel:
    async def test_empty_topic(self, team_ready):
        from miniapp_server import app
        client = TestClient(app)
        resp = client.post(
            "/api/generate/carousel",
            json={"topic": ""},
            headers=HEADERS,
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "empty_topic"

    async def test_valid_carousel_creates_stub(self, team_ready):
        from miniapp_server import app
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/generate/carousel",
            json={"topic": "Morning ritual with oils"},
            headers=HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "draft_id" in data
        assert data["kind"] == "carousel"


# ---------------------------------------------------------------------------
# POST /api/generate/threads-series — validation
# ---------------------------------------------------------------------------

class TestGenerateThreadsSeries:
    async def test_empty_topic(self, team_ready):
        from miniapp_server import app
        client = TestClient(app)
        resp = client.post(
            "/api/generate/threads-series",
            json={"topic": "", "goal_key": "trust", "emotion": "calm"},
            headers=HEADERS,
        )
        assert resp.status_code == 400

    async def test_invalid_goal(self, team_ready):
        from miniapp_server import app
        client = TestClient(app)
        resp = client.post(
            "/api/generate/threads-series",
            json={"topic": "test", "goal_key": "invalid_goal", "emotion": "calm"},
            headers=HEADERS,
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "invalid_goal"


# ---------------------------------------------------------------------------
# POST /api/suggest-topics
# ---------------------------------------------------------------------------

class TestSuggestTopics:
    @patch("miniapp.api.routers.create.suggest_topics", new_callable=AsyncMock)
    async def test_suggest_returns_topics(self, mock_suggest, team_ready):
        from miniapp_server import app
        mock_suggest.return_value = ["topic 1", "topic 2"]
        client = TestClient(app)
        resp = client.post(
            "/api/suggest-topics",
            json={"goal_key": "trust", "format_key": "instagram"},
            headers=HEADERS,
        )
        assert resp.status_code == 200
        assert len(resp.json()["topics"]) == 2
