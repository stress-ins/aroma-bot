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

    async def test_defaults_when_no_goal_emotion(self, team_ready):
        """Back-compat: POST without goal_key/emotion defaults to trust/calm."""
        from miniapp_server import app
        from bot.services.drafts_store import get_draft
        client = TestClient(app, raise_server_exceptions=False)
        with patch("miniapp.api.routers.create.complete_carousel_generation", new_callable=AsyncMock):
            resp = client.post(
                "/api/generate/carousel",
                json={"topic": "Morning ritual"},
                headers=HEADERS,
            )
        assert resp.status_code == 200
        draft_id = resp.json()["draft_id"]
        draft = await get_draft(draft_id)
        assert draft is not None
        assert draft.payload.get("goal_key") == "trust"
        assert draft.payload.get("emotion") == "calm"

    async def test_goal_emotion_saved_in_payload(self, team_ready):
        """POST with goal_key/emotion stores them in draft.payload."""
        from miniapp_server import app
        from bot.services.drafts_store import get_draft
        client = TestClient(app, raise_server_exceptions=False)
        with patch("miniapp.api.routers.create.complete_carousel_generation", new_callable=AsyncMock):
            resp = client.post(
                "/api/generate/carousel",
                json={"topic": "Evening ritual", "goal_key": "sales", "emotion": "inspiration"},
                headers=HEADERS,
            )
        assert resp.status_code == 200
        draft_id = resp.json()["draft_id"]
        draft = await get_draft(draft_id)
        assert draft is not None
        assert draft.payload.get("goal_key") == "sales"
        assert draft.payload.get("emotion") == "inspiration"

    async def test_invalid_goal_falls_back_to_default(self, team_ready):
        """Unknown goal_key is coerced to the trust default (not 400)."""
        from miniapp_server import app
        from bot.services.drafts_store import get_draft
        client = TestClient(app, raise_server_exceptions=False)
        with patch("miniapp.api.routers.create.complete_carousel_generation", new_callable=AsyncMock):
            resp = client.post(
                "/api/generate/carousel",
                json={"topic": "Any", "goal_key": "invalid_goal", "emotion": "calm"},
                headers=HEADERS,
            )
        assert resp.status_code == 200
        draft_id = resp.json()["draft_id"]
        draft = await get_draft(draft_id)
        assert draft is not None
        assert draft.payload.get("goal_key") == "trust"
        assert draft.payload.get("emotion") == "calm"

    async def test_invalid_emotion_falls_back_to_default(self, team_ready):
        """Unknown emotion is coerced to the calm default (not 400)."""
        from miniapp_server import app
        from bot.services.drafts_store import get_draft
        client = TestClient(app, raise_server_exceptions=False)
        with patch("miniapp.api.routers.create.complete_carousel_generation", new_callable=AsyncMock):
            resp = client.post(
                "/api/generate/carousel",
                json={"topic": "Any", "goal_key": "trust", "emotion": "rage"},
                headers=HEADERS,
            )
        assert resp.status_code == 200
        draft_id = resp.json()["draft_id"]
        draft = await get_draft(draft_id)
        assert draft is not None
        assert draft.payload.get("goal_key") == "trust"
        assert draft.payload.get("emotion") == "calm"

    async def test_values_normalized_uppercase_whitespace(self, team_ready):
        """Values are normalized via .strip().lower()."""
        from miniapp_server import app
        from bot.services.drafts_store import get_draft
        client = TestClient(app, raise_server_exceptions=False)
        with patch("miniapp.api.routers.create.complete_carousel_generation", new_callable=AsyncMock):
            resp = client.post(
                "/api/generate/carousel",
                json={"topic": "Any", "goal_key": "  AUTHORITY  ", "emotion": " Joy "},
                headers=HEADERS,
            )
        assert resp.status_code == 200
        draft_id = resp.json()["draft_id"]
        draft = await get_draft(draft_id)
        assert draft is not None
        assert draft.payload.get("goal_key") == "authority"
        assert draft.payload.get("emotion") == "joy"

    async def test_background_task_receives_goal_emotion(self, team_ready):
        """Background task is invoked with goal_key and emotion kwargs."""
        from miniapp_server import app
        client = TestClient(app, raise_server_exceptions=False)
        with patch("miniapp.api.routers.create.complete_carousel_generation", new_callable=AsyncMock) as mock_gen:
            resp = client.post(
                "/api/generate/carousel",
                json={"topic": "Some topic", "goal_key": "engagement", "emotion": "curiosity"},
                headers=HEADERS,
            )
        assert resp.status_code == 200
        # FastAPI's BackgroundTasks runs async tasks via `await`, so the AsyncMock
        # records an await — assert that explicitly to avoid ambiguity.
        assert mock_gen.await_count == 1
        call = mock_gen.call_args
        kwargs = call.kwargs
        assert kwargs.get("goal_key") == "engagement"
        assert kwargs.get("emotion") == "curiosity"

    async def test_oversize_goal_key_rejected(self, team_ready):
        """goal_key longer than 64 chars must be rejected with 422 (pydantic validation)."""
        from miniapp_server import app
        client = TestClient(app, raise_server_exceptions=False)
        oversize = "x" * 65
        resp = client.post(
            "/api/generate/carousel",
            json={"topic": "Test", "goal_key": oversize, "emotion": "calm"},
            headers=HEADERS,
        )
        assert resp.status_code == 422

    async def test_oversize_emotion_rejected(self, team_ready):
        """emotion longer than 64 chars must be rejected with 422 (pydantic validation)."""
        from miniapp_server import app
        client = TestClient(app, raise_server_exceptions=False)
        oversize = "y" * 65
        resp = client.post(
            "/api/generate/carousel",
            json={"topic": "Test", "goal_key": "trust", "emotion": oversize},
            headers=HEADERS,
        )
        assert resp.status_code == 422


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
# PATCH /api/youtube/{id}/section/{index}
# ---------------------------------------------------------------------------

class TestYouTubeSectionPatch:
    async def test_patch_section_not_found(self, team_ready):
        from miniapp_server import app
        client = TestClient(app)
        resp = client.patch(
            "/api/youtube/nonexistent/section/0",
            json={"speaker_text": "hello"},
            headers=HEADERS,
        )
        assert resp.status_code == 404

    async def test_patch_section_wrong_kind(self, team_ready):
        from bot.services.drafts_store import save_draft
        draft = await save_draft(
            kind="instagram", topic="t", source="ai", payload={},
            team_id=team_ready.team_id, created_by=12345,
        )
        from miniapp_server import app
        client = TestClient(app)
        resp = client.patch(
            f"/api/youtube/{draft.draft_id}/section/0",
            json={"speaker_text": "hello"},
            headers=HEADERS,
        )
        assert resp.status_code == 404

    async def test_patch_section_invalid_index(self, team_ready):
        from bot.services.drafts_store import save_draft
        draft = await save_draft(
            kind="youtube_video", topic="YT", source="ai",
            payload={"sections": [{"speaker_text": "original"}]},
            team_id=team_ready.team_id, created_by=12345,
        )
        from miniapp_server import app
        client = TestClient(app)
        resp = client.patch(
            f"/api/youtube/{draft.draft_id}/section/5",
            json={"speaker_text": "hello"},
            headers=HEADERS,
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "invalid_section_index"

    async def test_patch_section_success(self, team_ready):
        from bot.services.drafts_store import save_draft, get_draft
        draft = await save_draft(
            kind="youtube_video", topic="YT", source="ai",
            payload={"sections": [
                {"speaker_text": "original text", "label": "Intro"},
                {"speaker_text": "second section", "label": "Main"},
            ]},
            team_id=team_ready.team_id, created_by=12345,
        )
        from miniapp_server import app
        client = TestClient(app)
        resp = client.patch(
            f"/api/youtube/{draft.draft_id}/section/0",
            json={"speaker_text": "edited text"},
            headers=HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["section_index"] == 0

        # Verify the section was updated
        updated = await get_draft(draft.draft_id)
        assert updated.payload["sections"][0]["speaker_text"] == "edited text"
        # Verify version history was saved
        assert len(updated.payload["sections"][0]["versions"]) == 1
        assert updated.payload["sections"][0]["versions"][0]["text"] == "original text"
        # Verify second section wasn't modified
        assert updated.payload["sections"][1]["speaker_text"] == "second section"


class TestYouTubeRegenScriptWithNote:
    async def test_regen_script_with_revision_note(self, team_ready):
        from bot.services.drafts_store import save_draft
        draft = await save_draft(
            kind="youtube_video", topic="YT", source="ai",
            payload={"subformat": "talking_head"},
            team_id=team_ready.team_id, created_by=12345,
        )
        from miniapp_server import app
        client = TestClient(app, raise_server_exceptions=False)
        with patch("miniapp.api.routers.create.complete_youtube_regen_script", new_callable=AsyncMock):
            resp = client.post(
                f"/api/youtube/{draft.draft_id}/regen-script",
                json={"revision_note": "add more humor"},
                headers=HEADERS,
            )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        # Verify pending state was set
        from bot.services.drafts_store import get_draft
        updated = await get_draft(draft.draft_id)
        assert updated.payload.get("generation_pending") is True
        assert updated.payload.get("generation_stage") == "script"


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
