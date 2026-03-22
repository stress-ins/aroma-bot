"""Tests for the drafts API router (miniapp/api/routers/drafts.py).

Covers all 12 endpoints:
  GET  /api/drafts
  GET  /api/drafts/{id}
  POST /api/drafts/{id}/status
  DELETE /api/drafts/{id}
  POST /api/drafts/{id}/feedback
  POST /api/drafts/{id}/content
  POST /api/drafts/{id}/content/polish
  GET  /api/drafts/{id}/revisions
  GET  /api/drafts/{id}/revisions/{rev_num}
  POST /api/drafts/{id}/revisions/{rev_num}/restore
  POST /api/drafts/{id}/move
  POST /api/drafts/{id}/send
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _bypass_auth(monkeypatch):
    monkeypatch.setenv("AROMA_BYPASS_AUTH", "1")


HEADERS = {
    "X-Telegram-Init-Data": "user=%7B%22id%22%3A12345%7D&auth_date=9999999999&hash=abc",
}


@pytest.fixture()
async def team_with_drafts(setup_test_db):
    """Seed a team with a few draft records for testing."""
    from bot.services.team_store import create_team
    from bot.services.drafts_store import save_draft

    team = await create_team("Drafts Test Team", creator_telegram_id=12345)

    d1 = await save_draft(
        kind="instagram",
        topic="Lavender benefits",
        source="manual",
        payload={"caption": "Great post about lavender", "hook": "Did you know?"},
        team_id=team.team_id,
        created_by=12345,
    )
    d2 = await save_draft(
        kind="reels",
        topic="Morning routine",
        source="ai",
        payload={"scenario": "Wake up with essential oils"},
        team_id=team.team_id,
        created_by=12345,
    )
    d3 = await save_draft(
        kind="carousel",
        topic="Top 5 oils",
        source="manual",
        payload={"slides": ["Slide 1", "Slide 2", "Slide 3"]},
        team_id=team.team_id,
        created_by=12345,
    )
    return team, [d1, d2, d3]


# ---------------------------------------------------------------------------
# GET /api/drafts — list
# ---------------------------------------------------------------------------

class TestListDrafts:
    async def test_list_returns_items(self, team_with_drafts):
        team, drafts = team_with_drafts
        from miniapp_server import app
        client = TestClient(app)
        resp = client.get(
            "/api/drafts",
            headers={**HEADERS, "X-Team-Id": team.team_id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert data["total"] == 3

    async def test_list_filter_by_kind(self, team_with_drafts):
        team, drafts = team_with_drafts
        from miniapp_server import app
        client = TestClient(app)
        resp = client.get(
            "/api/drafts?kind=reels",
            headers={**HEADERS, "X-Team-Id": team.team_id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["kind"] == "reels"

    async def test_list_filter_by_query(self, team_with_drafts):
        team, drafts = team_with_drafts
        from miniapp_server import app
        client = TestClient(app)
        resp = client.get(
            "/api/drafts?query=lavender",
            headers={**HEADERS, "X-Team-Id": team.team_id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert "lavender" in data["items"][0]["topic"].lower()

    async def test_list_with_limit(self, team_with_drafts):
        team, drafts = team_with_drafts
        from miniapp_server import app
        client = TestClient(app)
        resp = client.get(
            "/api/drafts?limit=2",
            headers={**HEADERS, "X-Team-Id": team.team_id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 2

    async def test_list_with_include_metrics(self, team_with_drafts):
        team, drafts = team_with_drafts
        d1 = drafts[0]
        # Mark d1 as published and add metrics
        from bot.services.drafts_store import update_draft
        from bot.services.post_metrics_store import save_metrics
        await update_draft(d1.draft_id, status="published")
        await save_metrics(d1.draft_id, "threads", "ext_1", {"views": 100, "likes": 5, "replies": 2})

        from miniapp_server import app
        client = TestClient(app)
        resp = client.get(
            "/api/drafts?include_metrics=true",
            headers={**HEADERS, "X-Team-Id": team.team_id},
        )
        assert resp.status_code == 200
        data = resp.json()
        published_items = [it for it in data["items"] if it["status"] == "published"]
        assert len(published_items) == 1
        assert "metrics_summary" in published_items[0]
        ms = published_items[0]["metrics_summary"]
        assert ms["likes"] == 5
        assert ms["views"] == 100

    async def test_list_without_include_metrics(self, team_with_drafts):
        """By default metrics_summary is not included."""
        team, drafts = team_with_drafts
        from miniapp_server import app
        client = TestClient(app)
        resp = client.get(
            "/api/drafts",
            headers={**HEADERS, "X-Team-Id": team.team_id},
        )
        assert resp.status_code == 200
        data = resp.json()
        for item in data["items"]:
            assert "metrics_summary" not in item

    async def test_list_empty(self, setup_test_db):
        """List returns empty when no drafts exist (but team is auto-created)."""
        from miniapp_server import app
        client = TestClient(app)
        resp = client.get("/api/drafts", headers=HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0


# ---------------------------------------------------------------------------
# GET /api/drafts/{draft_id} — detail
# ---------------------------------------------------------------------------

class TestDraftDetail:
    async def test_detail_found(self, team_with_drafts):
        team, drafts = team_with_drafts
        d1 = drafts[0]
        from miniapp_server import app
        client = TestClient(app)
        resp = client.get(f"/api/drafts/{d1.draft_id}", headers=HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["draft_id"] == d1.draft_id
        assert data["kind"] == "instagram"
        assert data["topic"] == "Lavender benefits"
        assert "payload" in data

    async def test_detail_not_found(self, setup_test_db):
        from miniapp_server import app
        client = TestClient(app)
        resp = client.get("/api/drafts/nonexistent", headers=HEADERS)
        assert resp.status_code == 404
        assert resp.json()["detail"] == "draft_not_found"


# ---------------------------------------------------------------------------
# POST /api/drafts/{draft_id}/status
# ---------------------------------------------------------------------------

class TestUpdateStatus:
    async def test_update_status_success(self, team_with_drafts):
        team, drafts = team_with_drafts
        d1 = drafts[0]
        from miniapp_server import app
        client = TestClient(app)
        resp = client.post(
            f"/api/drafts/{d1.draft_id}/status",
            json={"status": "approved"},
            headers=HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"

    async def test_update_status_invalid(self, team_with_drafts):
        team, drafts = team_with_drafts
        d1 = drafts[0]
        from miniapp_server import app
        client = TestClient(app)
        resp = client.post(
            f"/api/drafts/{d1.draft_id}/status",
            json={"status": "garbage"},
            headers=HEADERS,
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "invalid_status"

    async def test_update_status_not_found(self, setup_test_db):
        from miniapp_server import app
        client = TestClient(app)
        resp = client.post(
            "/api/drafts/nonexistent/status",
            json={"status": "draft"},
            headers=HEADERS,
        )
        assert resp.status_code == 404

    async def test_update_status_all_valid_values(self, team_with_drafts):
        """All five valid status values should be accepted."""
        team, drafts = team_with_drafts
        d1 = drafts[0]
        from miniapp_server import app
        client = TestClient(app)
        for status in ("draft", "in_review", "approved", "published", "rejected"):
            resp = client.post(
                f"/api/drafts/{d1.draft_id}/status",
                json={"status": status},
                headers=HEADERS,
            )
            assert resp.status_code == 200, f"status={status} failed"
            assert resp.json()["status"] == status


# ---------------------------------------------------------------------------
# DELETE /api/drafts/{draft_id}
# ---------------------------------------------------------------------------

class TestDeleteDraft:
    async def test_delete_success(self, team_with_drafts):
        team, drafts = team_with_drafts
        d1 = drafts[0]
        from miniapp_server import app
        client = TestClient(app)
        resp = client.delete(f"/api/drafts/{d1.draft_id}", headers=HEADERS)
        assert resp.status_code == 200
        assert resp.json() == {"ok": True, "draft_id": d1.draft_id}

        # Verify it's gone
        resp2 = client.get(f"/api/drafts/{d1.draft_id}", headers=HEADERS)
        assert resp2.status_code == 404

    async def test_delete_not_found(self, setup_test_db):
        from miniapp_server import app
        client = TestClient(app)
        resp = client.delete("/api/drafts/nonexistent", headers=HEADERS)
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/drafts/{draft_id}/feedback
# ---------------------------------------------------------------------------

class TestUpdateFeedback:
    async def test_feedback_worked(self, team_with_drafts):
        team, drafts = team_with_drafts
        d1 = drafts[0]
        from miniapp_server import app
        client = TestClient(app)
        resp = client.post(
            f"/api/drafts/{d1.draft_id}/feedback",
            json={"feedback": "worked"},
            headers=HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["feedback"] == "worked"

    async def test_feedback_missed(self, team_with_drafts):
        team, drafts = team_with_drafts
        d1 = drafts[0]
        from miniapp_server import app
        client = TestClient(app)
        resp = client.post(
            f"/api/drafts/{d1.draft_id}/feedback",
            json={"feedback": "missed"},
            headers=HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["feedback"] == "missed"

    async def test_feedback_clear(self, team_with_drafts):
        team, drafts = team_with_drafts
        d1 = drafts[0]
        from miniapp_server import app
        client = TestClient(app)
        resp = client.post(
            f"/api/drafts/{d1.draft_id}/feedback",
            json={"feedback": ""},
            headers=HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["feedback"] == ""

    async def test_feedback_invalid(self, team_with_drafts):
        team, drafts = team_with_drafts
        d1 = drafts[0]
        from miniapp_server import app
        client = TestClient(app)
        resp = client.post(
            f"/api/drafts/{d1.draft_id}/feedback",
            json={"feedback": "invalid_value"},
            headers=HEADERS,
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "invalid_feedback"

    async def test_feedback_not_found(self, setup_test_db):
        from miniapp_server import app
        client = TestClient(app)
        resp = client.post(
            "/api/drafts/nonexistent/feedback",
            json={"feedback": "worked"},
            headers=HEADERS,
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/drafts/{draft_id}/content
# ---------------------------------------------------------------------------

class TestUpdateContent:
    async def test_content_update_success(self, team_with_drafts):
        team, drafts = team_with_drafts
        d1 = drafts[0]  # instagram kind — editable
        from miniapp_server import app
        client = TestClient(app)
        resp = client.post(
            f"/api/drafts/{d1.draft_id}/content",
            json={
                "topic": "Updated topic",
                "angle": "New angle",
                "hook": "New hook",
                "caption": "New caption",
                "cta": "Follow us",
                "hashtags": "#oils #wellness",
                "visual_prompt": "A serene scene",
                "editor_notes": "Reviewed",
            },
            headers=HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["topic"] == "Updated topic"
        assert data["payload"]["hook"] == "New hook"
        assert data["payload"]["caption"] == "New caption"

    async def test_content_update_not_found(self, setup_test_db):
        from miniapp_server import app
        client = TestClient(app)
        resp = client.post(
            "/api/drafts/nonexistent/content",
            json={"topic": "x"},
            headers=HEADERS,
        )
        assert resp.status_code == 404

    async def test_content_update_non_editable_kind(self, team_with_drafts):
        """Carousel kind is not in EDITABLE_KINDS, should return 404."""
        team, drafts = team_with_drafts
        d3 = drafts[2]  # carousel
        from miniapp_server import app
        client = TestClient(app)
        resp = client.post(
            f"/api/drafts/{d3.draft_id}/content",
            json={"topic": "x"},
            headers=HEADERS,
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "content_draft_not_found"


# ---------------------------------------------------------------------------
# POST /api/drafts/{draft_id}/content/polish
# ---------------------------------------------------------------------------

class TestPolishContent:
    async def test_polish_no_api_key(self, team_with_drafts, monkeypatch):
        """When anthropic_api_key is empty, should return 400."""
        team, drafts = team_with_drafts
        d1 = drafts[0]
        from config import settings as _cfg
        monkeypatch.setattr(_cfg, "anthropic_api_key", "")
        from miniapp_server import app
        client = TestClient(app)
        resp = client.post(
            f"/api/drafts/{d1.draft_id}/content/polish",
            headers=HEADERS,
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "anthropic_not_configured"

    async def test_polish_success(self, team_with_drafts, monkeypatch):
        """Polish succeeds when API key is set and draft is editable."""
        team, drafts = team_with_drafts
        d1 = drafts[0]
        from config import settings as _cfg
        monkeypatch.setattr(_cfg, "anthropic_api_key", "test-key")

        polished_payload = {
            "caption": "Polished caption",
            "hook": "Polished hook",
            "angle": "Polished angle",
            "cta": "CTA",
            "hashtags": "#polished",
            "visual_prompt": "",
            "editor_notes": "",
        }
        mock_polish = AsyncMock(return_value=polished_payload)
        import miniapp.api.routers.drafts as _drafts_mod
        monkeypatch.setattr(_drafts_mod, "polish_content_review_draft", mock_polish)

        from miniapp_server import app
        client = TestClient(app)
        resp = client.post(
            f"/api/drafts/{d1.draft_id}/content/polish",
            headers=HEADERS,
        )
        assert resp.status_code == 200
        mock_polish.assert_called_once_with(d1.draft_id)

    async def test_polish_not_found(self, team_with_drafts, monkeypatch):
        """Polish on non-existent draft returns 404."""
        from config import settings as _cfg
        monkeypatch.setattr(_cfg, "anthropic_api_key", "test-key")

        mock_polish = AsyncMock(return_value=None)
        import miniapp.api.routers.drafts as _drafts_mod
        monkeypatch.setattr(_drafts_mod, "polish_content_review_draft", mock_polish)

        from miniapp_server import app
        client = TestClient(app)
        resp = client.post(
            "/api/drafts/nonexistent/content/polish",
            headers=HEADERS,
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/drafts/{draft_id}/revisions
# ---------------------------------------------------------------------------

class TestListRevisions:
    async def test_revisions_empty(self, team_with_drafts):
        team, drafts = team_with_drafts
        d1 = drafts[0]
        from miniapp_server import app
        client = TestClient(app)
        resp = client.get(
            f"/api/drafts/{d1.draft_id}/revisions",
            headers=HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["items"] == []

    async def test_revisions_after_content_update(self, team_with_drafts):
        """After content update, a revision should be created."""
        team, drafts = team_with_drafts
        d1 = drafts[0]
        from miniapp_server import app
        client = TestClient(app)

        # Update content to trigger revision creation
        client.post(
            f"/api/drafts/{d1.draft_id}/content",
            json={
                "topic": "Edited",
                "angle": "a", "hook": "h", "caption": "c",
                "cta": "", "hashtags": "", "visual_prompt": "", "editor_notes": "",
            },
            headers=HEADERS,
        )

        resp = client.get(
            f"/api/drafts/{d1.draft_id}/revisions",
            headers=HEADERS,
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) >= 1
        assert items[0]["author"] == "user"
        assert items[0]["note"] == "manual save"

    async def test_revisions_not_found_draft(self, setup_test_db):
        from miniapp_server import app
        client = TestClient(app)
        resp = client.get("/api/drafts/nonexistent/revisions", headers=HEADERS)
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/drafts/{draft_id}/revisions/{rev_num}
# ---------------------------------------------------------------------------

class TestGetRevision:
    async def test_get_specific_revision(self, team_with_drafts):
        team, drafts = team_with_drafts
        d1 = drafts[0]
        from bot.services.draft_revisions_store import create_revision
        await create_revision(d1.draft_id, {"caption": "rev1"}, author="user", note="v1")

        from miniapp_server import app
        client = TestClient(app)
        resp = client.get(
            f"/api/drafts/{d1.draft_id}/revisions/1",
            headers=HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["rev_num"] == 1
        assert data["payload"]["caption"] == "rev1"

    async def test_get_revision_not_found(self, team_with_drafts):
        team, drafts = team_with_drafts
        d1 = drafts[0]
        from miniapp_server import app
        client = TestClient(app)
        resp = client.get(
            f"/api/drafts/{d1.draft_id}/revisions/999",
            headers=HEADERS,
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "revision_not_found"


# ---------------------------------------------------------------------------
# POST /api/drafts/{draft_id}/revisions/{rev_num}/restore
# ---------------------------------------------------------------------------

class TestRestoreRevision:
    async def test_restore_revision(self, team_with_drafts):
        team, drafts = team_with_drafts
        d1 = drafts[0]
        from bot.services.draft_revisions_store import create_revision

        # Create two revisions
        await create_revision(d1.draft_id, {"caption": "version1"}, author="user", note="v1")
        await create_revision(d1.draft_id, {"caption": "version2"}, author="user", note="v2")

        from miniapp_server import app
        client = TestClient(app)

        # Restore to revision 1
        resp = client.post(
            f"/api/drafts/{d1.draft_id}/revisions/1/restore",
            headers=HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["payload"]["caption"] == "version1"

        # Check that snapshot + restore revisions were created
        rev_resp = client.get(
            f"/api/drafts/{d1.draft_id}/revisions",
            headers=HEADERS,
        )
        revisions = rev_resp.json()["items"]
        # 2 original + 1 snapshot + 1 restore = 4
        assert len(revisions) == 4
        assert "snapshot before restore" in revisions[2]["note"]
        assert "restored from rev 1" in revisions[3]["note"]

    async def test_restore_revision_not_found(self, team_with_drafts):
        team, drafts = team_with_drafts
        d1 = drafts[0]
        from miniapp_server import app
        client = TestClient(app)
        resp = client.post(
            f"/api/drafts/{d1.draft_id}/revisions/999/restore",
            headers=HEADERS,
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/drafts/{draft_id}/move
# ---------------------------------------------------------------------------

class TestMoveDraft:
    async def test_move_success(self, team_with_drafts):
        team, drafts = team_with_drafts
        d1 = drafts[0]
        from bot.services.team_store import create_team, add_member
        target_team = await create_team("Target Team", creator_telegram_id=12345)

        from miniapp_server import app
        client = TestClient(app)
        resp = client.post(
            f"/api/drafts/{d1.draft_id}/move",
            json={"target_team_id": target_team.team_id},
            headers={**HEADERS, "X-Team-Id": team.team_id},
        )
        assert resp.status_code == 200

    async def test_move_not_found(self, team_with_drafts):
        team, drafts = team_with_drafts
        from miniapp_server import app
        client = TestClient(app)
        resp = client.post(
            "/api/drafts/nonexistent/move",
            json={"target_team_id": "some-team"},
            headers={**HEADERS, "X-Team-Id": team.team_id},
        )
        assert resp.status_code == 404

    async def test_move_insufficient_role(self, team_with_drafts):
        """User not in target team should get 403."""
        team, drafts = team_with_drafts
        d1 = drafts[0]
        from bot.services.team_store import create_team
        # Create team with a different user as creator
        target_team = await create_team("Other Team", creator_telegram_id=99999)

        from miniapp_server import app
        client = TestClient(app)
        resp = client.post(
            f"/api/drafts/{d1.draft_id}/move",
            json={"target_team_id": target_team.team_id},
            headers={**HEADERS, "X-Team-Id": team.team_id},
        )
        assert resp.status_code == 403
        assert resp.json()["detail"] == "insufficient_role_in_target_team"


# ---------------------------------------------------------------------------
# POST /api/drafts/{draft_id}/send
# ---------------------------------------------------------------------------

class TestSendDraft:
    async def test_send_not_configured(self, team_with_drafts, monkeypatch):
        """Without telegram config, should return 400."""
        team, drafts = team_with_drafts
        d1 = drafts[0]
        from config import settings as _cfg
        monkeypatch.setattr(_cfg, "telegram_bot_token", "")
        monkeypatch.setattr(_cfg, "report_target_chat_id", "")

        from miniapp_server import app
        client = TestClient(app)
        resp = client.post(
            f"/api/drafts/{d1.draft_id}/send",
            headers=HEADERS,
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "telegram_not_configured"

    async def test_send_not_found(self, setup_test_db):
        from miniapp_server import app
        client = TestClient(app)
        resp = client.post("/api/drafts/nonexistent/send", headers=HEADERS)
        assert resp.status_code == 404

    async def test_send_success(self, team_with_drafts, monkeypatch):
        """Successful send via mocked Bot."""
        team, drafts = team_with_drafts
        d1 = drafts[0]
        from config import settings as _cfg
        monkeypatch.setattr(_cfg, "telegram_bot_token", "fake-token")
        monkeypatch.setattr(_cfg, "report_target_chat_id", "-100123456")

        mock_bot_instance = MagicMock()
        mock_bot_instance.send_message = AsyncMock()
        mock_bot_cls = MagicMock(return_value=mock_bot_instance)

        import miniapp.api.routers.drafts as _drafts_router
        monkeypatch.setattr(_drafts_router, "Bot", mock_bot_cls)

        from miniapp_server import app
        client = TestClient(app)
        resp = client.post(
            f"/api/drafts/{d1.draft_id}/send",
            headers=HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
        mock_bot_instance.send_message.assert_called_once()
        call_kwargs = mock_bot_instance.send_message.call_args
        # User's telegram_id (12345) is parsed from initData header and used as chat_id
        assert "12345" in str(call_kwargs)


# ---------------------------------------------------------------------------
# _draft_chat_message helper
# ---------------------------------------------------------------------------

class TestDraftChatMessage:
    def test_carousel_message(self):
        from miniapp.api.routers.drafts import _draft_chat_message
        draft = MagicMock()
        draft.kind = "carousel"
        draft.topic = "Top oils"
        draft.payload = {"slides": ["Slide A", "Slide B"]}
        msg = _draft_chat_message(draft)
        assert "Карусель" in msg
        assert "Top oils" in msg
        assert "1. Slide A" in msg
        assert "2. Slide B" in msg

    def test_reels_message(self):
        from miniapp.api.routers.drafts import _draft_chat_message
        draft = MagicMock()
        draft.kind = "reels"
        draft.topic = "Morning routine"
        draft.payload = {"scenario": "A calming morning"}
        msg = _draft_chat_message(draft)
        assert "Рилс" in msg
        assert "Morning routine" in msg
        assert "A calming morning" in msg

    def test_reels_v2_message_with_upload_link(self):
        from miniapp.api.routers.drafts import _draft_chat_message
        draft = MagicMock()
        draft.kind = "reels_v2"
        draft.topic = "Lavender ritual"
        draft.draft_id = "abc123"
        draft.payload = {"concept": "A soothing concept", "video_status": "none"}
        msg = _draft_chat_message(draft)
        assert "Рилс" in msg
        assert "Lavender ritual" in msg
        assert "A soothing concept" in msg
        assert "upload_abc123" in msg

    def test_reels_v2_message_video_passed(self):
        from miniapp.api.routers.drafts import _draft_chat_message
        draft = MagicMock()
        draft.kind = "reels_v2"
        draft.topic = "Gong session"
        draft.draft_id = "def456"
        draft.payload = {"concept": "Healing sounds", "video_status": "passed"}
        msg = _draft_chat_message(draft)
        assert "Рилс" in msg
        assert "upload_def456" not in msg

    def test_generic_message_caption(self):
        from miniapp.api.routers.drafts import _draft_chat_message
        draft = MagicMock()
        draft.kind = "instagram"
        draft.topic = "Daily oils"
        draft.payload = {"caption": "Use oils daily"}
        msg = _draft_chat_message(draft)
        assert "Instagram" in msg
        assert "Daily oils" in msg
        assert "Use oils daily" in msg

    def test_generic_message_hook_fallback(self):
        from miniapp.api.routers.drafts import _draft_chat_message
        draft = MagicMock()
        draft.kind = "threads"
        draft.topic = "Wellness"
        draft.payload = {"hook": "Did you know?"}
        msg = _draft_chat_message(draft)
        assert "Did you know?" in msg

    def test_generic_message_angle_fallback(self):
        from miniapp.api.routers.drafts import _draft_chat_message
        draft = MagicMock()
        draft.kind = "telegram"
        draft.topic = "Tips"
        draft.payload = {"angle": "Expert angle"}
        msg = _draft_chat_message(draft)
        assert "Expert angle" in msg


# ---------------------------------------------------------------------------
# Auth enforcement (when bypass is OFF)
# ---------------------------------------------------------------------------

class TestAuthEnforcement:
    async def test_no_auth_header_returns_403(self, setup_test_db, monkeypatch):
        monkeypatch.delenv("AROMA_BYPASS_AUTH", raising=False)
        from miniapp_server import app
        client = TestClient(app)
        resp = client.get("/api/drafts/some-id")
        assert resp.status_code == 403

    async def test_no_auth_header_on_list_returns_403(self, setup_test_db, monkeypatch):
        monkeypatch.delenv("AROMA_BYPASS_AUTH", raising=False)
        from miniapp_server import app
        client = TestClient(app)
        resp = client.get("/api/drafts")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Edge cases: filter combinations and status transitions
# ---------------------------------------------------------------------------

class TestFilterCombinations:
    async def test_filter_by_status(self, team_with_drafts):
        team, drafts = team_with_drafts
        d1 = drafts[0]
        from bot.services.drafts_store import update_draft
        await update_draft(d1.draft_id, status="approved")

        from miniapp_server import app
        client = TestClient(app)
        resp = client.get(
            "/api/drafts?status=approved",
            headers={**HEADERS, "X-Team-Id": team.team_id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["status"] == "approved"

    async def test_filter_by_feedback(self, team_with_drafts):
        team, drafts = team_with_drafts
        d1 = drafts[0]
        from bot.services.drafts_store import update_draft
        await update_draft(d1.draft_id, feedback="worked")

        from miniapp_server import app
        client = TestClient(app)
        resp = client.get(
            "/api/drafts?feedback=worked",
            headers={**HEADERS, "X-Team-Id": team.team_id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
