"""Tests for threads_series API router — slot editing, regen, history, approve, publish."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from bot.services.drafts_store import DraftRecord
from miniapp.api.auth import _require_auth
from miniapp.api.routers.threads_series import router


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_draft(
    draft_id: str = "ts01",
    kind: str = "threads_series",
    status: str = "draft",
    payload: dict | None = None,
    topic: str = "Ароматерапия зимой",
) -> DraftRecord:
    return DraftRecord(
        draft_id=draft_id,
        kind=kind,
        topic=topic,
        source="test",
        created_at=datetime.now(timezone.utc).isoformat(),
        status=status,
        feedback="",
        payload=payload or {
            "goal": "trust",
            "series_summary": "Серия о зимних ароматах",
            "threads_posts": [
                {"slot": "morning", "text": "Утренний пост", "why_it_works": "hook"},
                {"slot": "day", "text": "Дневной пост", "why_it_works": "value"},
                {"slot": "evening", "text": "Вечерний пост", "why_it_works": "emotion"},
            ],
        },
    )


def _serialized_draft(draft: DraftRecord) -> dict:
    """Minimal serialized representation for mocking serialize_draft."""
    return {
        "draft_id": draft.draft_id,
        "kind": draft.kind,
        "topic": draft.topic,
        "status": draft.status,
        "payload": draft.payload,
    }


@pytest.fixture
def ts_app():
    """FastAPI app with threads_series router and auth bypassed."""
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[_require_auth] = lambda: None
    yield app


@pytest.fixture
def client(ts_app):
    return TestClient(ts_app)


# ---------------------------------------------------------------------------
# PATCH /api/threads-series/{draft_id}/slot
# ---------------------------------------------------------------------------

class TestPatchSlot:
    def test_patch_slot_updates_text(self, client):
        draft = _make_draft()
        updated_draft = _make_draft()
        updated_draft.payload["threads_posts"][0]["text"] = "Новый текст"

        with (
            patch("miniapp.api.routers.threads_series.get_draft", new_callable=AsyncMock, return_value=draft),
            patch("miniapp.api.routers.threads_series.update_draft", new_callable=AsyncMock, return_value=updated_draft),
            patch("miniapp.api.routers.threads_series.serialize_draft", new_callable=AsyncMock, return_value=_serialized_draft(updated_draft)),
        ):
            resp = client.patch("/api/threads-series/ts01/slot", json={
                "slot": "morning",
                "text": "Новый текст",
            })
        assert resp.status_code == 200
        assert resp.json()["draft_id"] == "ts01"

    def test_patch_slot_updates_scheduled_time(self, client):
        draft = _make_draft()
        with (
            patch("miniapp.api.routers.threads_series.get_draft", new_callable=AsyncMock, return_value=draft),
            patch("miniapp.api.routers.threads_series.update_draft", new_callable=AsyncMock, return_value=draft),
            patch("miniapp.api.routers.threads_series.serialize_draft", new_callable=AsyncMock, return_value=_serialized_draft(draft)),
        ):
            resp = client.patch("/api/threads-series/ts01/slot", json={
                "slot": "day",
                "scheduled_time": "14:00",
            })
        assert resp.status_code == 200

    def test_patch_slot_not_found(self, client):
        draft = _make_draft()
        with patch("miniapp.api.routers.threads_series.get_draft", new_callable=AsyncMock, return_value=draft):
            resp = client.patch("/api/threads-series/ts01/slot", json={
                "slot": "nonexistent",
                "text": "abc",
            })
        assert resp.status_code == 404
        assert resp.json()["detail"] == "slot_not_found"

    def test_patch_slot_draft_not_found(self, client):
        with patch("miniapp.api.routers.threads_series.get_draft", new_callable=AsyncMock, return_value=None):
            resp = client.patch("/api/threads-series/ts01/slot", json={
                "slot": "morning",
                "text": "abc",
            })
        assert resp.status_code == 404
        assert resp.json()["detail"] == "threads_series_not_found"

    def test_patch_slot_wrong_kind(self, client):
        draft = _make_draft(kind="reels")
        with patch("miniapp.api.routers.threads_series.get_draft", new_callable=AsyncMock, return_value=draft):
            resp = client.patch("/api/threads-series/ts01/slot", json={
                "slot": "morning",
                "text": "abc",
            })
        assert resp.status_code == 404
        assert resp.json()["detail"] == "threads_series_not_found"

    def test_patch_slot_update_draft_returns_none(self, client):
        draft = _make_draft()
        with (
            patch("miniapp.api.routers.threads_series.get_draft", new_callable=AsyncMock, return_value=draft),
            patch("miniapp.api.routers.threads_series.update_draft", new_callable=AsyncMock, return_value=None),
        ):
            resp = client.patch("/api/threads-series/ts01/slot", json={
                "slot": "morning",
                "text": "abc",
            })
        assert resp.status_code == 404
        assert resp.json()["detail"] == "draft_not_found"


# ---------------------------------------------------------------------------
# POST /api/threads-series/{draft_id}/regen-slot
# ---------------------------------------------------------------------------

class TestRegenSlot:
    def test_regen_slot_success(self, client):
        draft = _make_draft()
        updated = _make_draft()
        updated.payload["threads_posts"][1]["text"] = "Regenerated text"

        with (
            patch("miniapp.api.routers.threads_series.get_draft", new_callable=AsyncMock, return_value=draft),
            patch("miniapp.api.routers.threads_series._regen_slot_text", new_callable=AsyncMock, return_value=("Regenerated text", "why")),
            patch("miniapp.api.routers.threads_series.update_draft", new_callable=AsyncMock, return_value=updated),
            patch("miniapp.api.routers.threads_series.serialize_draft", new_callable=AsyncMock, return_value=_serialized_draft(updated)),
        ):
            resp = client.post("/api/threads-series/ts01/regen-slot", json={
                "slot": "day",
                "note": "Make it funnier",
            })
        assert resp.status_code == 200

    def test_regen_slot_saves_version_history(self, client):
        draft = _make_draft()
        original_text = draft.payload["threads_posts"][0]["text"]

        saved_payload = {}

        async def capture_update(draft_id, **kwargs):
            saved_payload.update(kwargs.get("payload", {}))
            return _make_draft()

        with (
            patch("miniapp.api.routers.threads_series.get_draft", new_callable=AsyncMock, return_value=draft),
            patch("miniapp.api.routers.threads_series._regen_slot_text", new_callable=AsyncMock, return_value=("New text", "why")),
            patch("miniapp.api.routers.threads_series.update_draft", side_effect=capture_update),
            patch("miniapp.api.routers.threads_series.serialize_draft", new_callable=AsyncMock, return_value=_serialized_draft(draft)),
        ):
            resp = client.post("/api/threads-series/ts01/regen-slot", json={
                "slot": "morning",
            })
        assert resp.status_code == 200
        # Verify old text was saved in versions
        morning_post = next(p for p in saved_payload["threads_posts"] if p["slot"] == "morning")
        assert len(morning_post["versions"]) == 1
        assert morning_post["versions"][0]["text"] == original_text

    def test_regen_slot_not_found(self, client):
        draft = _make_draft()
        with patch("miniapp.api.routers.threads_series.get_draft", new_callable=AsyncMock, return_value=draft):
            resp = client.post("/api/threads-series/ts01/regen-slot", json={
                "slot": "nonexistent",
            })
        assert resp.status_code == 404
        assert resp.json()["detail"] == "slot_not_found"

    def test_regen_slot_draft_not_found(self, client):
        with patch("miniapp.api.routers.threads_series.get_draft", new_callable=AsyncMock, return_value=None):
            resp = client.post("/api/threads-series/ts01/regen-slot", json={
                "slot": "morning",
            })
        assert resp.status_code == 404

    def test_regen_slot_update_returns_none(self, client):
        draft = _make_draft()
        with (
            patch("miniapp.api.routers.threads_series.get_draft", new_callable=AsyncMock, return_value=draft),
            patch("miniapp.api.routers.threads_series._regen_slot_text", new_callable=AsyncMock, return_value=("text", "why")),
            patch("miniapp.api.routers.threads_series.update_draft", new_callable=AsyncMock, return_value=None),
        ):
            resp = client.post("/api/threads-series/ts01/regen-slot", json={
                "slot": "morning",
            })
        assert resp.status_code == 404
        assert resp.json()["detail"] == "draft_not_found"


# ---------------------------------------------------------------------------
# GET /api/threads-series/{draft_id}/slot-history/{slot}
# ---------------------------------------------------------------------------

class TestSlotHistory:
    def test_slot_history_returns_versions(self, client):
        draft = _make_draft()
        draft.payload["threads_posts"][0]["versions"] = [
            {"text": "v1", "created_at": "2026-01-01T00:00:00"},
            {"text": "v2", "created_at": "2026-01-02T00:00:00"},
        ]
        with patch("miniapp.api.routers.threads_series.get_draft", new_callable=AsyncMock, return_value=draft):
            resp = client.get("/api/threads-series/ts01/slot-history/morning")
        assert resp.status_code == 200
        data = resp.json()
        assert data["slot"] == "morning"
        assert len(data["versions"]) == 2

    def test_slot_history_empty_versions(self, client):
        draft = _make_draft()
        with patch("miniapp.api.routers.threads_series.get_draft", new_callable=AsyncMock, return_value=draft):
            resp = client.get("/api/threads-series/ts01/slot-history/morning")
        assert resp.status_code == 200
        assert resp.json()["versions"] == []

    def test_slot_history_slot_not_found(self, client):
        draft = _make_draft()
        with patch("miniapp.api.routers.threads_series.get_draft", new_callable=AsyncMock, return_value=draft):
            resp = client.get("/api/threads-series/ts01/slot-history/nonexistent")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "slot_not_found"

    def test_slot_history_draft_not_found(self, client):
        with patch("miniapp.api.routers.threads_series.get_draft", new_callable=AsyncMock, return_value=None):
            resp = client.get("/api/threads-series/ts01/slot-history/morning")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/threads-series/{draft_id}/regenerate-posts
# ---------------------------------------------------------------------------

class TestRegeneratePosts:
    def test_regenerate_posts_success(self, client):
        draft = _make_draft()
        new_payload = {
            "series_summary": "New summary",
            "threads_posts": [
                {"slot": "morning", "text": "new morning"},
                {"slot": "day", "text": "new day"},
                {"slot": "evening", "text": "new evening"},
            ],
        }
        saved = _make_draft(payload=new_payload)

        with (
            patch("miniapp.api.routers.threads_series.get_draft", new_callable=AsyncMock, return_value=draft),
            patch("bot.agents.generate_content_draft", new_callable=AsyncMock, return_value={"text": "raw"}),
            patch("bot.services.miniapp_generator.build_threads_series_payload", return_value=new_payload),
            patch("miniapp.api.routers.threads_series.update_draft", new_callable=AsyncMock, return_value=saved),
            patch("miniapp.api.routers.threads_series.serialize_draft", new_callable=AsyncMock, return_value=_serialized_draft(saved)),
        ):
            resp = client.post("/api/threads-series/ts01/regenerate-posts")
        assert resp.status_code == 200

    def test_regenerate_posts_preserves_series_summary(self, client):
        draft = _make_draft()
        draft.payload["series_summary"] = "Original summary"

        # New payload has empty summary
        new_payload = {
            "series_summary": "",
            "threads_posts": [{"slot": "morning", "text": "m"}],
        }

        captured = {}

        async def capture_update(draft_id, **kwargs):
            captured.update(kwargs)
            return _make_draft()

        with (
            patch("miniapp.api.routers.threads_series.get_draft", new_callable=AsyncMock, return_value=draft),
            patch("bot.agents.generate_content_draft", new_callable=AsyncMock, return_value={}),
            patch("bot.services.miniapp_generator.build_threads_series_payload", return_value=new_payload),
            patch("miniapp.api.routers.threads_series.update_draft", side_effect=capture_update),
            patch("miniapp.api.routers.threads_series.serialize_draft", new_callable=AsyncMock, return_value=_serialized_draft(draft)),
        ):
            resp = client.post("/api/threads-series/ts01/regenerate-posts")
        assert resp.status_code == 200
        assert captured["payload"]["series_summary"] == "Original summary"

    def test_regenerate_posts_no_posts_produced(self, client):
        draft = _make_draft()
        new_payload = {"threads_posts": []}

        with (
            patch("miniapp.api.routers.threads_series.get_draft", new_callable=AsyncMock, return_value=draft),
            patch("bot.agents.generate_content_draft", new_callable=AsyncMock, return_value={}),
            patch("bot.services.miniapp_generator.build_threads_series_payload", return_value=new_payload),
        ):
            resp = client.post("/api/threads-series/ts01/regenerate-posts")
        assert resp.status_code == 502
        assert resp.json()["detail"] == "generation_produced_no_posts"

    def test_regenerate_posts_draft_not_found(self, client):
        with patch("miniapp.api.routers.threads_series.get_draft", new_callable=AsyncMock, return_value=None):
            resp = client.post("/api/threads-series/ts01/regenerate-posts")
        assert resp.status_code == 404

    def test_regenerate_posts_update_returns_none(self, client):
        draft = _make_draft()
        new_payload = {
            "threads_posts": [{"slot": "morning", "text": "m"}],
        }
        with (
            patch("miniapp.api.routers.threads_series.get_draft", new_callable=AsyncMock, return_value=draft),
            patch("bot.agents.generate_content_draft", new_callable=AsyncMock, return_value={}),
            patch("bot.services.miniapp_generator.build_threads_series_payload", return_value=new_payload),
            patch("miniapp.api.routers.threads_series.update_draft", new_callable=AsyncMock, return_value=None),
        ):
            resp = client.post("/api/threads-series/ts01/regenerate-posts")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "draft_not_found"


# ---------------------------------------------------------------------------
# POST /api/threads-series/{draft_id}/approve
# ---------------------------------------------------------------------------

class TestApproveSeries:
    def test_approve_success(self, client):
        draft = _make_draft()
        approved = _make_draft(status="approved")

        with (
            patch("miniapp.api.routers.threads_series.get_draft", new_callable=AsyncMock, return_value=draft),
            patch("miniapp.api.routers.threads_series.update_draft", new_callable=AsyncMock, return_value=approved),
            patch("miniapp.api.routers.threads_series.serialize_draft", new_callable=AsyncMock, return_value=_serialized_draft(approved)),
        ):
            resp = client.post("/api/threads-series/ts01/approve")
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"

    def test_approve_no_posts(self, client):
        draft = _make_draft(payload={"threads_posts": []})
        with patch("miniapp.api.routers.threads_series.get_draft", new_callable=AsyncMock, return_value=draft):
            resp = client.post("/api/threads-series/ts01/approve")
        assert resp.status_code == 400
        assert resp.json()["detail"] == "no_posts_to_approve"

    def test_approve_draft_not_found(self, client):
        with patch("miniapp.api.routers.threads_series.get_draft", new_callable=AsyncMock, return_value=None):
            resp = client.post("/api/threads-series/ts01/approve")
        assert resp.status_code == 404

    def test_approve_update_returns_none(self, client):
        draft = _make_draft()
        with (
            patch("miniapp.api.routers.threads_series.get_draft", new_callable=AsyncMock, return_value=draft),
            patch("miniapp.api.routers.threads_series.update_draft", new_callable=AsyncMock, return_value=None),
        ):
            resp = client.post("/api/threads-series/ts01/approve")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "draft_not_found"


# ---------------------------------------------------------------------------
# POST /api/threads-series/{draft_id}/slots/{slot}/publish-now
# ---------------------------------------------------------------------------

class TestPublishSlotNow:
    def test_publish_slot_success(self, client):
        draft = _make_draft(status="approved")
        with (
            patch("miniapp.api.routers.threads_series.get_draft", new_callable=AsyncMock, return_value=draft),
            patch("bot.services.publisher.publish_threads_series_slot", new_callable=AsyncMock, return_value={"ok": True}),
        ):
            resp = client.post("/api/threads-series/ts01/slots/morning/publish-now")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["slot"] == "morning"

    def test_publish_slot_already_published(self, client):
        draft = _make_draft(status="approved")
        draft.payload["threads_posts"][0]["status"] = "published"
        with patch("miniapp.api.routers.threads_series.get_draft", new_callable=AsyncMock, return_value=draft):
            resp = client.post("/api/threads-series/ts01/slots/morning/publish-now")
        assert resp.status_code == 200
        assert resp.json()["status"] == "already_published"

    def test_publish_slot_not_approved(self, client):
        draft = _make_draft(status="draft")
        with patch("miniapp.api.routers.threads_series.get_draft", new_callable=AsyncMock, return_value=draft):
            resp = client.post("/api/threads-series/ts01/slots/morning/publish-now")
        assert resp.status_code == 400
        assert resp.json()["detail"] == "draft_must_be_approved_or_scheduled"

    def test_publish_slot_scheduled_status_allowed(self, client):
        draft = _make_draft(status="scheduled")
        with (
            patch("miniapp.api.routers.threads_series.get_draft", new_callable=AsyncMock, return_value=draft),
            patch("bot.services.publisher.publish_threads_series_slot", new_callable=AsyncMock, return_value={"ok": True}),
        ):
            resp = client.post("/api/threads-series/ts01/slots/day/publish-now")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_publish_slot_not_found(self, client):
        draft = _make_draft(status="approved")
        with patch("miniapp.api.routers.threads_series.get_draft", new_callable=AsyncMock, return_value=draft):
            resp = client.post("/api/threads-series/ts01/slots/nonexistent/publish-now")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "slot_not_found"

    def test_publish_slot_draft_not_found(self, client):
        with patch("miniapp.api.routers.threads_series.get_draft", new_callable=AsyncMock, return_value=None):
            resp = client.post("/api/threads-series/ts01/slots/morning/publish-now")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/threads-series/{draft_id}/publish-now
# ---------------------------------------------------------------------------

class TestPublishSeriesNow:
    def test_publish_series_success(self, client):
        draft = _make_draft(status="approved")
        updated = _make_draft(status="published")

        with (
            patch("miniapp.api.routers.threads_series.get_draft", new_callable=AsyncMock, side_effect=[draft, updated]),
            patch("bot.services.publisher.publish_threads_series_slot", new_callable=AsyncMock, return_value={"slot": "morning", "status": "ok"}),
            patch("miniapp.api.routers.threads_series.asyncio.sleep", new_callable=AsyncMock),
        ):
            resp = client.post("/api/threads-series/ts01/publish-now")
        assert resp.status_code == 200
        data = resp.json()
        assert data["draft_id"] == "ts01"
        assert len(data["results"]) == 3

    def test_publish_series_no_posts(self, client):
        draft = _make_draft(status="approved", payload={"threads_posts": []})
        with patch("miniapp.api.routers.threads_series.get_draft", new_callable=AsyncMock, return_value=draft):
            resp = client.post("/api/threads-series/ts01/publish-now")
        assert resp.status_code == 400
        assert resp.json()["detail"] == "no_posts_to_publish"

    def test_publish_series_not_approved(self, client):
        draft = _make_draft(status="draft")
        with patch("miniapp.api.routers.threads_series.get_draft", new_callable=AsyncMock, return_value=draft):
            resp = client.post("/api/threads-series/ts01/publish-now")
        assert resp.status_code == 400
        assert resp.json()["detail"] == "draft_must_be_approved_or_scheduled"

    def test_publish_series_skips_already_published(self, client):
        draft = _make_draft(status="approved")
        draft.payload["threads_posts"][0]["status"] = "published"
        updated = _make_draft(status="published")

        with (
            patch("miniapp.api.routers.threads_series.get_draft", new_callable=AsyncMock, side_effect=[draft, updated]),
            patch("bot.services.publisher.publish_threads_series_slot", new_callable=AsyncMock, return_value={"slot": "day", "status": "ok"}),
            patch("miniapp.api.routers.threads_series.asyncio.sleep", new_callable=AsyncMock),
        ):
            resp = client.post("/api/threads-series/ts01/publish-now")
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert results[0]["status"] == "already_published"

    def test_publish_series_handles_slot_errors(self, client):
        draft = _make_draft(status="approved")
        updated = _make_draft(status="approved")

        async def fail_publish(draft_id, slot):
            raise RuntimeError("API error")

        with (
            patch("miniapp.api.routers.threads_series.get_draft", new_callable=AsyncMock, side_effect=[draft, updated]),
            patch("bot.services.publisher.publish_threads_series_slot", side_effect=fail_publish),
            patch("miniapp.api.routers.threads_series.asyncio.sleep", new_callable=AsyncMock),
            patch("bot.handlers.monitor.notify_owner", new_callable=AsyncMock),
        ):
            resp = client.post("/api/threads-series/ts01/publish-now")
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert all(r["status"] == "error" for r in results)

    def test_publish_series_draft_not_found(self, client):
        with patch("miniapp.api.routers.threads_series.get_draft", new_callable=AsyncMock, return_value=None):
            resp = client.post("/api/threads-series/ts01/publish-now")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# _require_threads_series helper
# ---------------------------------------------------------------------------

class TestRequireThreadsSeries:
    def test_rejects_none(self):
        from miniapp.api.routers.threads_series import _require_threads_series
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            _require_threads_series(None)
        assert exc_info.value.status_code == 404

    def test_rejects_wrong_kind(self):
        from miniapp.api.routers.threads_series import _require_threads_series
        from fastapi import HTTPException
        draft = _make_draft(kind="reels")
        with pytest.raises(HTTPException) as exc_info:
            _require_threads_series(draft)
        assert exc_info.value.status_code == 404

    def test_accepts_threads_series(self):
        from miniapp.api.routers.threads_series import _require_threads_series
        draft = _make_draft(kind="threads_series")
        result = _require_threads_series(draft)
        assert result is draft


# ---------------------------------------------------------------------------
# _hard_truncate helper
# ---------------------------------------------------------------------------

class TestHardTruncate:
    def test_short_text_unchanged(self):
        from miniapp.api.routers.threads_series import _hard_truncate
        assert _hard_truncate("Hello world.", 500) == "Hello world."

    def test_truncates_at_sentence_boundary(self):
        from miniapp.api.routers.threads_series import _hard_truncate
        text = "First sentence. Second sentence. Third sentence is very long and goes over."
        result = _hard_truncate(text, 40)
        assert result == "First sentence. Second sentence."
        assert len(result) <= 40

    def test_truncates_at_newline(self):
        from miniapp.api.routers.threads_series import _hard_truncate
        text = "Line one\nLine two which is quite long and should be cut"
        result = _hard_truncate(text, 15)
        assert result == "Line one"

    def test_no_sentence_boundary_falls_back(self):
        from miniapp.api.routers.threads_series import _hard_truncate
        text = "a" * 600
        result = _hard_truncate(text, 500)
        assert len(result) == 500


# ---------------------------------------------------------------------------
# _ANALYSIS_RE detection
# ---------------------------------------------------------------------------

class TestAnalysisDetection:
    def test_detects_review_patterns(self):
        from miniapp.api.routers.threads_series import _ANALYSIS_RE
        assert _ANALYSIS_RE.match("Отличный пост, но есть несколько замечаний:")
        assert _ANALYSIS_RE.match("Что работает: глубокая идея")
        assert _ANALYSIS_RE.match("Замечания: текст длинноват")
        assert _ANALYSIS_RE.match("Анализ: разберём пост")
        assert _ANALYSIS_RE.match("Рекомендации: сократить")
        assert _ANALYSIS_RE.match("✅ Что работает")

    def test_no_false_positive_on_normal_posts(self):
        from miniapp.api.routers.threads_series import _ANALYSIS_RE
        assert not _ANALYSIS_RE.match("Благодарность за 5 минут перед встречей")
        assert not _ANALYSIS_RE.match("Ты когда-нибудь замечал")
        assert not _ANALYSIS_RE.match("Отличная погода")
        assert not _ANALYSIS_RE.match("Запахи — это портал в прошлое")
