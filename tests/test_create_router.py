"""Tests for the create API router (miniapp/api/routers/create.py).

Covers validation of content generation endpoints:
  POST /api/suggest-topics
  POST /api/generate/content
  POST /api/generate/carousel
  POST /api/generate/threads-series
  POST /api/generate/reels
  POST /api/generate/content-series
  POST /api/generate/youtube
  POST /api/youtube/{id}/regen-script
  POST /api/youtube/{id}/thumbnail
  POST /api/youtube/{id}/metadata
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
        with patch("miniapp.api.routers.create.complete_content_generation", new_callable=AsyncMock):
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
        with patch("miniapp.api.routers.create.complete_carousel_generation", new_callable=AsyncMock):
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


# ---------------------------------------------------------------------------
# POST /api/generate/reels
# ---------------------------------------------------------------------------

class TestGenerateReels:
    async def test_empty_topic(self, team_ready):
        from miniapp_server import app
        client = TestClient(app)
        resp = client.post(
            "/api/generate/reels",
            json={"topic": "", "goal": "trust", "emotion": "calm"},
            headers=HEADERS,
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "empty_topic"

    async def test_valid_reels_creates_stub(self, team_ready):
        from miniapp_server import app
        client = TestClient(app, raise_server_exceptions=False)
        with patch("miniapp.api.routers.create.complete_reels_v2_generation", new_callable=AsyncMock):
            resp = client.post(
                "/api/generate/reels",
                json={"topic": "Morning aromatherapy", "goal": "trust", "emotion": "calm"},
                headers=HEADERS,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "draft_id" in data
        assert data["kind"] == "reels_v2"

    async def test_lightweight_reels(self, team_ready):
        from miniapp_server import app
        client = TestClient(app, raise_server_exceptions=False)
        with patch("miniapp.api.routers.create.complete_reels_lightweight_generation", new_callable=AsyncMock):
            resp = client.post(
                "/api/generate/reels",
                json={"topic": "Quick oils", "goal": "trust", "emotion": "calm", "lightweight": True},
                headers=HEADERS,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["kind"] == "reels_v2"


# ---------------------------------------------------------------------------
# POST /api/generate/content-series
# ---------------------------------------------------------------------------

class TestGenerateContentSeries:
    async def test_empty_topic(self, team_ready):
        from miniapp_server import app
        client = TestClient(app)
        resp = client.post(
            "/api/generate/content-series",
            json={"topic": "", "goal_key": "trust", "format_key": "instagram"},
            headers=HEADERS,
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "empty_topic"

    async def test_invalid_goal(self, team_ready):
        from miniapp_server import app
        client = TestClient(app)
        resp = client.post(
            "/api/generate/content-series",
            json={"topic": "test", "goal_key": "bad_goal"},
            headers=HEADERS,
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "invalid_goal"

    async def test_valid_creates_stub(self, team_ready):
        from miniapp_server import app
        client = TestClient(app, raise_server_exceptions=False)
        with patch("miniapp.api.routers.create.complete_series_generation", new_callable=AsyncMock):
            resp = client.post(
                "/api/generate/content-series",
                json={"topic": "Weekly oil tips", "goal_key": "trust", "format_key": "instagram", "post_count": 5},
                headers=HEADERS,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "draft_id" in data
        assert data["kind"] == "content_series"


# ---------------------------------------------------------------------------
# POST /api/generate/youtube
# ---------------------------------------------------------------------------

class TestGenerateYouTube:
    async def test_empty_topic(self, team_ready):
        from miniapp_server import app
        client = TestClient(app)
        resp = client.post(
            "/api/generate/youtube",
            json={"topic": "", "subformat": "talking_head"},
            headers=HEADERS,
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "empty_topic"

    async def test_invalid_subformat(self, team_ready):
        from miniapp_server import app
        client = TestClient(app)
        resp = client.post(
            "/api/generate/youtube",
            json={"topic": "test", "subformat": "invalid_format"},
            headers=HEADERS,
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "invalid_subformat"

    async def test_valid_creates_stub(self, team_ready):
        from miniapp_server import app
        client = TestClient(app, raise_server_exceptions=False)
        with patch("miniapp.api.routers.create.complete_youtube_generation", new_callable=AsyncMock):
            resp = client.post(
                "/api/generate/youtube",
                json={"topic": "Essential oils guide", "subformat": "talking_head"},
                headers=HEADERS,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "draft_id" in data
        assert data["kind"] == "youtube_video"


# ---------------------------------------------------------------------------
# POST /api/youtube/{id}/regen-script
# ---------------------------------------------------------------------------

class TestYouTubeRegenScript:
    async def test_regen_script_not_found(self, team_ready):
        from miniapp_server import app
        client = TestClient(app)
        resp = client.post("/api/youtube/nonexistent/regen-script", headers=HEADERS)
        assert resp.status_code == 404
        assert resp.json()["detail"] == "draft_not_found"

    async def test_regen_script_wrong_kind(self, team_ready):
        from bot.services.drafts_store import save_draft
        draft = await save_draft(
            kind="instagram", topic="t", source="ai", payload={},
            team_id=team_ready.team_id, created_by=12345,
        )
        from miniapp_server import app
        client = TestClient(app)
        resp = client.post(f"/api/youtube/{draft.draft_id}/regen-script", headers=HEADERS)
        assert resp.status_code == 404

    async def test_regen_script_success(self, team_ready):
        from bot.services.drafts_store import save_draft
        draft = await save_draft(
            kind="youtube_video", topic="YT", source="ai",
            payload={"subformat": "talking_head"},
            team_id=team_ready.team_id, created_by=12345,
        )
        from miniapp_server import app
        client = TestClient(app, raise_server_exceptions=False)
        with patch("miniapp.api.routers.create.complete_youtube_regen_script", new_callable=AsyncMock):
            resp = client.post(f"/api/youtube/{draft.draft_id}/regen-script", headers=HEADERS)
        assert resp.status_code == 200
        assert resp.json()["ok"] is True


# ---------------------------------------------------------------------------
# POST /api/youtube/{id}/thumbnail
# ---------------------------------------------------------------------------

class TestYouTubeThumbnail:
    async def test_thumbnail_not_found(self, team_ready):
        from miniapp_server import app
        client = TestClient(app)
        resp = client.post(
            "/api/youtube/nonexistent/thumbnail",
            json={"mode": "prompt"},
            headers=HEADERS,
        )
        assert resp.status_code == 404

    async def test_thumbnail_success(self, team_ready):
        from bot.services.drafts_store import save_draft
        draft = await save_draft(
            kind="youtube_video", topic="YT", source="ai",
            payload={"subformat": "listicle"},
            team_id=team_ready.team_id, created_by=12345,
        )
        from miniapp_server import app
        client = TestClient(app, raise_server_exceptions=False)
        with patch("miniapp.api.routers.create.complete_youtube_generate_thumbnail", new_callable=AsyncMock):
            resp = client.post(
                f"/api/youtube/{draft.draft_id}/thumbnail",
                json={"mode": "prompt", "revision_note": "brighter"},
                headers=HEADERS,
            )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True


# ---------------------------------------------------------------------------
# POST /api/youtube/{id}/metadata
# ---------------------------------------------------------------------------

class TestYouTubeMetadata:
    async def test_metadata_not_found(self, team_ready):
        from miniapp_server import app
        client = TestClient(app)
        resp = client.post("/api/youtube/nonexistent/metadata", headers=HEADERS)
        assert resp.status_code == 404

    async def test_metadata_success(self, team_ready):
        from bot.services.drafts_store import save_draft
        draft = await save_draft(
            kind="youtube_video", topic="YT", source="ai",
            payload={"subformat": "podcast"},
            team_id=team_ready.team_id, created_by=12345,
        )
        from miniapp_server import app
        client = TestClient(app, raise_server_exceptions=False)
        with patch("miniapp.api.routers.create.complete_youtube_generate_metadata", new_callable=AsyncMock):
            resp = client.post(f"/api/youtube/{draft.draft_id}/metadata", headers=HEADERS)
        assert resp.status_code == 200
        assert resp.json()["ok"] is True


# ---------------------------------------------------------------------------
# _validate_topic helper
# ---------------------------------------------------------------------------

class TestValidateTopic:
    async def test_no_api_key(self, team_ready, monkeypatch):
        from config import settings
        monkeypatch.setattr(settings, "anthropic_api_key", "")
        from miniapp_server import app
        client = TestClient(app)
        resp = client.post(
            "/api/generate/content",
            json={"topic": "test", "goal_key": "trust", "format_key": "instagram"},
            headers=HEADERS,
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "anthropic_not_configured"
