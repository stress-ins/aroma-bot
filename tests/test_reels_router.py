"""Tests for miniapp/api/routers/reels.py — reels API endpoints.

Groups:
  - List & Detail
  - Frame editing (patch, note, prompt, fields)
  - Generation endpoints (regen-concept, regen-scenario, regen-frame-image, generate-images, regen-caption)
  - Approve, feedback, export, scenario update
  - Compose & compose-status
  - Publish & retry-platform
  - Video status & check-video
  - Storyboard & frames regenerate-all
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from miniapp.api.routers.reels import router, _compose_status
from miniapp.api.auth import _require_auth, _resolve_telegram_id


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_DRAFT = {
    "draft_id": "r01",
    "topic": "lavender morning",
    "frame_count": 2,
    "approved": False,
    "generation_pending": False,
    "generation_stage": "",
    "payload": {"goal": "trust", "emotion": "calm"},
    "frames": [
        {"id": "f1", "scene": "Open bottle", "timecode": "0-3s", "angle": "close-up",
         "image_status": "ready", "image_versions": ["v1", "v2"], "image_url": "/img/f1.png"},
        {"id": "f2", "scene": "Diffuser mist", "timecode": "3-6s", "angle": "wide",
         "image_status": "pending", "image_versions": [], "image_url": ""},
    ],
}


@pytest.fixture
def reels_app():
    """Minimal FastAPI app with reels router, auth fully bypassed."""
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[_require_auth] = lambda: None
    app.dependency_overrides[_resolve_telegram_id] = lambda: 12345
    with (
        patch("miniapp.api.auth.get_or_create_user", new_callable=AsyncMock) as mock_get_user,
        patch("miniapp.api.auth.effective_tier", new_callable=AsyncMock, return_value="expert"),
    ):
        from db.models import UserProfile
        mock_user = MagicMock(spec=UserProfile)
        mock_user.tier = "expert"
        mock_user.trial_ends_at = None
        mock_get_user.return_value = mock_user
        yield app
    # Reset compose status between tests
    _compose_status.clear()


@pytest.fixture
def client(reels_app):
    with TestClient(reels_app) as c:
        yield c


# ---------------------------------------------------------------------------
# List & Detail
# ---------------------------------------------------------------------------

class TestReelsList:
    def test_list_reels(self, client):
        with patch("miniapp.api.routers.reels.list_reels_drafts", new_callable=AsyncMock, return_value=[SAMPLE_DRAFT]):
            resp = client.get("/api/reels")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["draft_id"] == "r01"

    def test_list_reels_empty(self, client):
        with patch("miniapp.api.routers.reels.list_reels_drafts", new_callable=AsyncMock, return_value=[]):
            resp = client.get("/api/reels")
        assert resp.status_code == 200
        assert resp.json() == {"items": [], "total": 0}

    def test_list_reels_custom_limit(self, client):
        with patch("miniapp.api.routers.reels.list_reels_drafts", new_callable=AsyncMock, return_value=[]) as mock_list:
            resp = client.get("/api/reels?limit=5")
        assert resp.status_code == 200
        mock_list.assert_called_once_with(limit=5)


class TestReelsDetail:
    def test_detail_found(self, client):
        with patch("miniapp.api.routers.reels.serialize_reels_draft", new_callable=AsyncMock, return_value=SAMPLE_DRAFT):
            resp = client.get("/api/reels/r01")
        assert resp.status_code == 200
        assert resp.json()["draft_id"] == "r01"

    def test_detail_not_found(self, client):
        with patch("miniapp.api.routers.reels.serialize_reels_draft", new_callable=AsyncMock, return_value=None):
            resp = client.get("/api/reels/missing")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "reels_not_found"


# ---------------------------------------------------------------------------
# Frame editing
# ---------------------------------------------------------------------------

class TestFrameEditing:
    def test_patch_frame(self, client):
        with patch("miniapp.api.routers.reels.update_frame_field", new_callable=AsyncMock, return_value=SAMPLE_DRAFT):
            resp = client.patch("/api/reels/r01/frame", json={"frame_id": "f1", "overlay_text": "new text"})
        assert resp.status_code == 200

    def test_patch_frame_empty_id(self, client):
        resp = client.patch("/api/reels/r01/frame", json={"frame_id": "  ", "overlay_text": "x"})
        assert resp.status_code == 400
        assert resp.json()["detail"] == "empty_frame_id"

    def test_patch_frame_not_found(self, client):
        with patch("miniapp.api.routers.reels.update_frame_field", new_callable=AsyncMock, return_value=None):
            resp = client.patch("/api/reels/r01/frame", json={"frame_id": "missing", "overlay_text": "x"})
        assert resp.status_code == 404

    def test_frame_note(self, client):
        with patch("miniapp.api.routers.reels.update_reels_frame_note", new_callable=AsyncMock, return_value=SAMPLE_DRAFT):
            resp = client.post("/api/reels/r01/frames/0/note", json={"note": "add warmth"})
        assert resp.status_code == 200

    def test_frame_note_not_found(self, client):
        with patch("miniapp.api.routers.reels.update_reels_frame_note", new_callable=AsyncMock, return_value=None):
            resp = client.post("/api/reels/r01/frames/0/note", json={"note": "x"})
        assert resp.status_code == 404

    def test_frame_prompt(self, client):
        with patch("miniapp.api.routers.reels.update_reels_frame_prompt", new_callable=AsyncMock, return_value=SAMPLE_DRAFT):
            resp = client.post("/api/reels/r01/frames/0/prompt", json={"prompt": "warm sunset"})
        assert resp.status_code == 200

    def test_frame_prompt_empty(self, client):
        resp = client.post("/api/reels/r01/frames/0/prompt", json={"prompt": "  "})
        assert resp.status_code == 400
        assert resp.json()["detail"] == "empty_prompt"

    def test_frame_fields(self, client):
        with patch("miniapp.api.routers.reels.update_reels_frame_fields", new_callable=AsyncMock, return_value=SAMPLE_DRAFT):
            resp = client.post("/api/reels/r01/frames/0/fields", json={"scene": "Open bottle", "angle": "close-up", "timecode": "0-3s"})
        assert resp.status_code == 200

    def test_frame_fields_not_found(self, client):
        with patch("miniapp.api.routers.reels.update_reels_frame_fields", new_callable=AsyncMock, return_value=None):
            resp = client.post("/api/reels/r01/frames/0/fields", json={"scene": "x"})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Generation endpoints (tier-gated, BackgroundTasks)
# ---------------------------------------------------------------------------

class TestGeneration:
    def test_regen_concept(self, client):
        with (
            patch("miniapp.api.routers.reels.serialize_reels_draft", new_callable=AsyncMock, return_value=SAMPLE_DRAFT),
            patch("miniapp.api.routers.reels.set_generation_state", new_callable=AsyncMock),
            patch("miniapp.api.routers.reels.complete_reels_v2_regen_concept_only", new_callable=AsyncMock),
        ):
            resp = client.post("/api/reels/r01/regen-concept")
        assert resp.status_code == 200

    def test_regen_concept_not_found(self, client):
        with patch("miniapp.api.routers.reels.serialize_reels_draft", new_callable=AsyncMock, return_value=None):
            resp = client.post("/api/reels/r01/regen-concept")
        assert resp.status_code == 404

    def test_regen_scenario(self, client):
        with (
            patch("miniapp.api.routers.reels.serialize_reels_draft", new_callable=AsyncMock, return_value=SAMPLE_DRAFT),
            patch("miniapp.api.routers.reels.set_generation_state", new_callable=AsyncMock),
            patch("miniapp.api.routers.reels.complete_reels_v2_regen_scenario_only", new_callable=AsyncMock),
        ):
            resp = client.post("/api/reels/r01/regen-scenario")
        assert resp.status_code == 200

    def test_regen_scenario_not_found(self, client):
        with patch("miniapp.api.routers.reels.serialize_reels_draft", new_callable=AsyncMock, return_value=None):
            resp = client.post("/api/reels/r01/regen-scenario")
        assert resp.status_code == 404

    def test_regen_frame_image(self, client):
        with (
            patch("miniapp.api.routers.reels.set_generation_state", new_callable=AsyncMock),
            patch("miniapp.api.routers.reels.serialize_reels_draft", new_callable=AsyncMock, return_value=SAMPLE_DRAFT),
            patch("miniapp.api.routers.reels.complete_reels_v2_regen_frame", new_callable=AsyncMock),
        ):
            resp = client.post("/api/reels/r01/regen-frame-image", json={"frame_id": "f1", "prompt": "sunset glow"})
        assert resp.status_code == 200

    def test_regen_frame_image_empty_id(self, client):
        resp = client.post("/api/reels/r01/regen-frame-image", json={"frame_id": " ", "prompt": "x"})
        assert resp.status_code == 400
        assert resp.json()["detail"] == "empty_frame_id"

    def test_generate_images(self, client):
        with (
            patch("miniapp.api.routers.reels.set_generation_state", new_callable=AsyncMock),
            patch("miniapp.api.routers.reels.serialize_reels_draft", new_callable=AsyncMock, return_value=SAMPLE_DRAFT),
            patch("miniapp.api.routers.reels.complete_reels_v2_generate_images", new_callable=AsyncMock),
        ):
            resp = client.post("/api/reels/r01/generate-images")
        assert resp.status_code == 200

    def test_generate_images_not_found(self, client):
        with (
            patch("miniapp.api.routers.reels.set_generation_state", new_callable=AsyncMock),
            patch("miniapp.api.routers.reels.serialize_reels_draft", new_callable=AsyncMock, return_value=None),
            patch("miniapp.api.routers.reels.complete_reels_v2_generate_images", new_callable=AsyncMock),
        ):
            resp = client.post("/api/reels/r01/generate-images")
        assert resp.status_code == 404

    def test_regen_caption(self, client):
        with (
            patch("miniapp.api.routers.reels.serialize_reels_draft", new_callable=AsyncMock, return_value=SAMPLE_DRAFT),
            patch("miniapp.api.routers.reels.set_generation_state", new_callable=AsyncMock),
            patch("miniapp.api.routers.reels.complete_reels_v2_regen_caption", new_callable=AsyncMock),
        ):
            resp = client.post("/api/reels/r01/regen-caption")
        assert resp.status_code == 200

    def test_regen_caption_not_found(self, client):
        with patch("miniapp.api.routers.reels.serialize_reels_draft", new_callable=AsyncMock, return_value=None):
            resp = client.post("/api/reels/r01/regen-caption")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Frame versions
# ---------------------------------------------------------------------------

class TestFrameVersions:
    def test_frame_versions_found(self, client):
        with patch("miniapp.api.routers.reels.serialize_reels_draft", new_callable=AsyncMock, return_value=SAMPLE_DRAFT):
            resp = client.get("/api/reels/r01/frame-versions/f1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["frame_id"] == "f1"
        assert data["versions"] == ["v1", "v2"]

    def test_frame_versions_frame_not_found(self, client):
        with patch("miniapp.api.routers.reels.serialize_reels_draft", new_callable=AsyncMock, return_value=SAMPLE_DRAFT):
            resp = client.get("/api/reels/r01/frame-versions/missing")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "frame_not_found"

    def test_frame_versions_draft_not_found(self, client):
        with patch("miniapp.api.routers.reels.serialize_reels_draft", new_callable=AsyncMock, return_value=None):
            resp = client.get("/api/reels/r01/frame-versions/f1")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Approve, feedback, export, scenario
# ---------------------------------------------------------------------------

class TestApproveAndFeedback:
    def test_approve(self, client):
        with patch("miniapp.api.routers.reels.approve_reels", new_callable=AsyncMock, return_value=SAMPLE_DRAFT):
            resp = client.patch("/api/reels/r01/approve", json={"shooting_deadline_days": 5})
        assert resp.status_code == 200

    def test_approve_not_found(self, client):
        with patch("miniapp.api.routers.reels.approve_reels", new_callable=AsyncMock, return_value=None):
            resp = client.patch("/api/reels/r01/approve", json={})
        assert resp.status_code == 404

    def test_feedback(self, client):
        with patch("miniapp.api.routers.reels.record_feedback", new_callable=AsyncMock, return_value=SAMPLE_DRAFT):
            resp = client.patch("/api/reels/r01/feedback", json={"platform": "instagram", "rating": 4, "reaction_types": ["like"]})
        assert resp.status_code == 200

    def test_feedback_not_found(self, client):
        with patch("miniapp.api.routers.reels.record_feedback", new_callable=AsyncMock, return_value=None):
            resp = client.patch("/api/reels/r01/feedback", json={"platform": "ig", "rating": 1})
        assert resp.status_code == 404

    def test_export(self, client):
        with patch("miniapp.api.routers.reels.build_reels_export_payload", new_callable=AsyncMock, return_value={"data": "export"}):
            resp = client.get("/api/reels/r01/export")
        assert resp.status_code == 200
        assert resp.json()["data"] == "export"

    def test_export_not_found(self, client):
        with patch("miniapp.api.routers.reels.build_reels_export_payload", new_callable=AsyncMock, return_value=None):
            resp = client.get("/api/reels/r01/export")
        assert resp.status_code == 404

    def test_scenario_update(self, client):
        with patch("miniapp.api.routers.reels.update_reels_scenario", new_callable=AsyncMock, return_value=SAMPLE_DRAFT):
            resp = client.post("/api/reels/r01/scenario", json={"scenario": "New scenario", "concept": "New concept"})
        assert resp.status_code == 200

    def test_scenario_update_not_found(self, client):
        with patch("miniapp.api.routers.reels.update_reels_scenario", new_callable=AsyncMock, return_value=None):
            resp = client.post("/api/reels/r01/scenario", json={"scenario": "x"})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Video status & check-video
# ---------------------------------------------------------------------------

class TestVideoStatus:
    def test_video_status(self, client):
        with patch("miniapp.api.routers.reels.serialize_reels_draft", new_callable=AsyncMock, return_value=SAMPLE_DRAFT):
            resp = client.get("/api/reels/r01/video-status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["draft_id"] == "r01"
        assert data["images_ready"] == 1  # only f1 has image_status=ready
        assert data["approved"] is False

    def test_video_status_not_found(self, client):
        with patch("miniapp.api.routers.reels.serialize_reels_draft", new_callable=AsyncMock, return_value=None):
            resp = client.get("/api/reels/r01/video-status")
        assert resp.status_code == 404

    def test_check_video(self, client):
        with patch("bot.services.reels_video.check_video_tech", new_callable=AsyncMock, return_value={"ok": True}):
            resp = client.post("/api/reels/r01/check-video")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_check_video_not_found(self, client):
        with patch("bot.services.reels_video.check_video_tech", new_callable=AsyncMock, return_value=None):
            resp = client.post("/api/reels/r01/check-video")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Publish & retry-platform
# ---------------------------------------------------------------------------

class TestPublish:
    def test_publish(self, client):
        with patch("bot.services.reels_video.publish_reels_video", new_callable=AsyncMock, return_value={"published": True}):
            resp = client.post("/api/reels/r01/publish", json={"platforms": ["instagram"], "date": "2026-04-01", "time": "10:00"})
        assert resp.status_code == 200
        assert resp.json()["published"] is True

    def test_publish_not_found(self, client):
        with patch("bot.services.reels_video.publish_reels_video", new_callable=AsyncMock, return_value=None):
            resp = client.post("/api/reels/r01/publish", json={"platforms": ["instagram"]})
        assert resp.status_code == 404

    def test_retry_platform(self, client):
        with patch("bot.services.reels_video.publish_reels_video", new_callable=AsyncMock, return_value={"retried": True}):
            resp = client.post("/api/reels/r01/retry-platform", json={"platform": "instagram"})
        assert resp.status_code == 200

    def test_retry_platform_not_found(self, client):
        with patch("bot.services.reels_video.publish_reels_video", new_callable=AsyncMock, return_value=None):
            resp = client.post("/api/reels/r01/retry-platform", json={"platform": "tiktok"})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Compose & compose-status
# ---------------------------------------------------------------------------

class TestCompose:
    def test_compose_starts(self, client):
        with (
            patch("miniapp.api.routers.reels.serialize_reels_draft", new_callable=AsyncMock, return_value=SAMPLE_DRAFT),
            patch("miniapp.api.routers.reels._run_compose_task", new_callable=AsyncMock),
        ):
            resp = client.post("/api/reels/r01/compose")
        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "pending"
        assert data["draft_id"] == "r01"

    def test_compose_not_found(self, client):
        with patch("miniapp.api.routers.reels.serialize_reels_draft", new_callable=AsyncMock, return_value=None):
            resp = client.post("/api/reels/missing/compose")
        assert resp.status_code == 404

    def test_compose_already_running(self, client):
        _compose_status["r01"] = {"status": "running", "error": None, "result": None}
        with patch("miniapp.api.routers.reels.serialize_reels_draft", new_callable=AsyncMock, return_value=SAMPLE_DRAFT):
            resp = client.post("/api/reels/r01/compose")
        assert resp.status_code == 409
        assert resp.json()["detail"] == "compose_already_running"

    def test_compose_status_not_started(self, client):
        draft_no_video = {**SAMPLE_DRAFT, "payload": {}}
        with patch("miniapp.api.routers.reels.serialize_reels_draft", new_callable=AsyncMock, return_value=draft_no_video):
            resp = client.get("/api/reels/r01/compose-status")
        assert resp.status_code == 200
        assert resp.json()["status"] == "not_started"

    def test_compose_status_completed_from_payload(self, client):
        draft_with_video = {**SAMPLE_DRAFT, "payload": {"video_ready": True, "video_path": "/v.mp4", "video_url": "/static/v.mp4"}}
        with patch("miniapp.api.routers.reels.serialize_reels_draft", new_callable=AsyncMock, return_value=draft_with_video):
            resp = client.get("/api/reels/r01/compose-status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert data["video_url"] == "/static/v.mp4"

    def test_compose_status_running(self, client):
        _compose_status["r01"] = {"status": "running", "error": None, "result": None}
        resp = client.get("/api/reels/r01/compose-status")
        assert resp.status_code == 200
        assert resp.json()["status"] == "running"

    def test_compose_status_failed(self, client):
        _compose_status["r01"] = {"status": "failed", "error": "timeout", "result": None}
        resp = client.get("/api/reels/r01/compose-status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "failed"
        assert data["error"] == "timeout"

    def test_compose_status_draft_not_found(self, client):
        with patch("miniapp.api.routers.reels.serialize_reels_draft", new_callable=AsyncMock, return_value=None):
            resp = client.get("/api/reels/missing/compose-status")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Storyboard & frames regenerate-all
# ---------------------------------------------------------------------------

class TestStoryboardRegenerate:
    def test_storyboard_regenerate(self, client):
        with (
            patch("miniapp.api.routers.reels.regenerate_reels_storyboard", new_callable=AsyncMock, return_value=SAMPLE_DRAFT),
            patch("miniapp.api.routers.reels.set_generation_state", new_callable=AsyncMock),
            patch("miniapp.api.routers.reels.serialize_reels_draft", new_callable=AsyncMock, return_value=SAMPLE_DRAFT),
            patch("miniapp.api.routers.reels.complete_reels_regenerate_all", new_callable=AsyncMock),
        ):
            resp = client.post("/api/reels/r01/storyboard/regenerate")
        assert resp.status_code == 200

    def test_storyboard_regenerate_not_found(self, client):
        with patch("miniapp.api.routers.reels.regenerate_reels_storyboard", new_callable=AsyncMock, return_value=None):
            resp = client.post("/api/reels/r01/storyboard/regenerate")
        assert resp.status_code == 404

    def test_frames_regenerate_all(self, client):
        with (
            patch("miniapp.api.routers.reels.set_generation_state", new_callable=AsyncMock),
            patch("miniapp.api.routers.reels.serialize_reels_draft", new_callable=AsyncMock, return_value=SAMPLE_DRAFT),
            patch("miniapp.api.routers.reels.complete_reels_regenerate_all", new_callable=AsyncMock),
        ):
            resp = client.post("/api/reels/r01/frames/regenerate-all")
        assert resp.status_code == 200

    def test_frames_regenerate_all_not_found(self, client):
        with (
            patch("miniapp.api.routers.reels.set_generation_state", new_callable=AsyncMock),
            patch("miniapp.api.routers.reels.serialize_reels_draft", new_callable=AsyncMock, return_value=None),
            patch("miniapp.api.routers.reels.complete_reels_regenerate_all", new_callable=AsyncMock),
        ):
            resp = client.post("/api/reels/r01/frames/regenerate-all")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Frame regenerate (single frame asset)
# ---------------------------------------------------------------------------

class TestFrameRegenerate:
    def test_frame_regenerate(self, client):
        with (
            patch("miniapp.api.routers.reels.regenerate_reels_frame_asset", new_callable=AsyncMock, return_value={"ok": True}),
            patch("miniapp.api.routers.reels.serialize_reels_draft", new_callable=AsyncMock, return_value=SAMPLE_DRAFT),
        ):
            resp = client.post("/api/reels/r01/frames/0/regenerate")
        assert resp.status_code == 200

    def test_frame_regenerate_failed(self, client):
        with patch("miniapp.api.routers.reels.regenerate_reels_frame_asset", new_callable=AsyncMock, return_value=None):
            resp = client.post("/api/reels/r01/frames/0/regenerate")
        assert resp.status_code == 503
        assert resp.json()["detail"] == "reels_frame_regenerate_failed"
