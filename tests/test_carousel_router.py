"""Tests for the carousel API router (miniapp/api/routers/carousel.py).

Covers:
  GET  /api/carousel/{id}
  POST /api/carousel/{id}/slides/{idx}/text
  POST /api/carousel/{id}/slides/{idx}/note
  POST /api/carousel/{id}/slides/{idx}/regenerate
  POST /api/carousel/{id}/slides/{idx}/versions/{v}/select
  DELETE /api/carousel/{id}/slides/{idx}/versions/{v}
  POST /api/carousel/{id}/layout
  POST /api/carousel/{id}/regenerate-all
  GET  /api/carousel/{id}/slides/{idx}/preview
  POST /api/carousel/{id}/preview
  GET  /api/carousel/{id}/pptx
  POST /api/carousel/{id}/pptx/import
  GET  /api/carousel/{id}/canva/status
  GET  /api/carousel/{id}/canva/task-status
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

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
async def carousel_draft(setup_test_db):
    from bot.services.team_store import create_team
    from bot.services.drafts_store import save_draft

    team = await create_team("Carousel Team", creator_telegram_id=12345)
    draft = await save_draft(
        kind="carousel",
        topic="Top 5 oils",
        source="ai",
        payload={
            "slides": [
                {"heading": "Slide 1", "body": "Body 1"},
                {"heading": "Slide 2", "body": "Body 2"},
                {"heading": "Slide 3", "body": "Body 3"},
            ],
            "img_prompts": ["prompt1", "prompt2", "prompt3"],
            "slide_images": [
                {"path": "img1.png", "prompt": "p1"},
                {"path": "img2.png", "prompt": "p2"},
                None,
            ],
            "slide_image_versions": [
                [{"path": "img1.png", "prompt": "p1"}],
                [{"path": "img2.png", "prompt": "p2"}],
                [],
            ],
            "layout_style": "overlay",
            "images_ready": 2,
        },
        team_id=team.team_id,
        created_by=12345,
    )
    return team, draft


def _client():
    from miniapp_server import app
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# GET /api/carousel/{draft_id}
# ---------------------------------------------------------------------------

class TestGetCarousel:
    async def test_get_carousel_success(self, carousel_draft):
        _, draft = carousel_draft
        client = _client()
        resp = client.get(f"/api/carousel/{draft.draft_id}", headers=HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["draft_id"] == draft.draft_id
        assert data["kind"] == "carousel"
        assert "payload" in data

    async def test_get_carousel_not_found(self, setup_test_db):
        client = _client()
        resp = client.get("/api/carousel/nonexistent", headers=HEADERS)
        assert resp.status_code == 404
        assert resp.json()["detail"] == "carousel_not_found"

    async def test_get_carousel_wrong_kind(self, setup_test_db):
        """Non-carousel draft should return 404."""
        from bot.services.team_store import create_team
        from bot.services.drafts_store import save_draft

        team = await create_team("T", creator_telegram_id=12345)
        draft = await save_draft(
            kind="instagram", topic="t", source="ai", payload={},
            team_id=team.team_id, created_by=12345,
        )
        client = _client()
        resp = client.get(f"/api/carousel/{draft.draft_id}", headers=HEADERS)
        assert resp.status_code == 404

    async def test_get_carousel_auto_triggers_image_gen(self, setup_test_db):
        """Carousel with img_prompts but no slide_images triggers auto-generation."""
        from bot.services.team_store import create_team
        from bot.services.drafts_store import save_draft

        team = await create_team("T", creator_telegram_id=12345)
        draft = await save_draft(
            kind="carousel", topic="auto gen", source="ai",
            payload={
                "slides": [{"heading": "S1"}],
                "img_prompts": ["prompt1"],
                # No slide_images, no generation_pending
            },
            team_id=team.team_id, created_by=12345,
        )
        client = _client()
        # The background task _auto_populate_carousel would run; patch it
        with patch(
            "bot.services.carousel_assets.populate_carousel_slide_assets",
            new_callable=AsyncMock, return_value="done",
        ):
            resp = client.get(f"/api/carousel/{draft.draft_id}", headers=HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        # Should have set generation_pending
        assert data["payload"].get("generation_pending") is True


# ---------------------------------------------------------------------------
# POST /api/carousel/{id}/slides/{idx}/text
# ---------------------------------------------------------------------------

class TestUpdateSlideText:
    async def test_update_text_success(self, carousel_draft):
        _, draft = carousel_draft
        client = _client()
        with patch(
            "miniapp.api.routers.carousel.update_carousel_slide_text",
            new_callable=AsyncMock, return_value={"slides": []},
        ):
            resp = client.post(
                f"/api/carousel/{draft.draft_id}/slides/0/text",
                json={"text": "New slide text"},
                headers=HEADERS,
            )
        assert resp.status_code == 200

    async def test_update_text_not_found(self, carousel_draft):
        _, draft = carousel_draft
        client = _client()
        with patch(
            "miniapp.api.routers.carousel.update_carousel_slide_text",
            new_callable=AsyncMock, return_value=None,
        ):
            resp = client.post(
                f"/api/carousel/{draft.draft_id}/slides/99/text",
                json={"text": "x"},
                headers=HEADERS,
            )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "carousel_slide_not_found"


# ---------------------------------------------------------------------------
# POST /api/carousel/{id}/slides/{idx}/note
# ---------------------------------------------------------------------------

class TestUpdateSlideNote:
    async def test_update_note_success(self, carousel_draft):
        _, draft = carousel_draft
        client = _client()
        with patch(
            "miniapp.api.routers.carousel.update_carousel_slide_note",
            new_callable=AsyncMock, return_value={"slides": []},
        ):
            resp = client.post(
                f"/api/carousel/{draft.draft_id}/slides/0/note",
                json={"note": "Review note"},
                headers=HEADERS,
            )
        assert resp.status_code == 200

    async def test_update_note_not_found(self, carousel_draft):
        _, draft = carousel_draft
        client = _client()
        with patch(
            "miniapp.api.routers.carousel.update_carousel_slide_note",
            new_callable=AsyncMock, return_value=None,
        ):
            resp = client.post(
                f"/api/carousel/{draft.draft_id}/slides/99/note",
                json={"note": "x"},
                headers=HEADERS,
            )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "carousel_slide_not_found"


# ---------------------------------------------------------------------------
# POST /api/carousel/{id}/slides/{idx}/regenerate
# ---------------------------------------------------------------------------

class TestRegenerateSlide:
    async def test_regenerate_slide_success(self, carousel_draft):
        _, draft = carousel_draft
        client = _client()
        with (
            patch("bot.services.draft_revisions_store.snapshot_before_regen", new_callable=AsyncMock),
            patch("miniapp.api.routers.carousel.complete_carousel_regen_slide", new_callable=AsyncMock),
            patch("miniapp.api.routers.carousel.set_generation_state", new_callable=AsyncMock),
        ):
            resp = client.post(
                f"/api/carousel/{draft.draft_id}/slides/0/regenerate",
                json={"note": "make it brighter"},
                headers=HEADERS,
            )
        assert resp.status_code == 200

    async def test_regenerate_slide_not_found(self, setup_test_db):
        client = _client()
        resp = client.post(
            "/api/carousel/nonexistent/slides/0/regenerate",
            json={},
            headers=HEADERS,
        )
        assert resp.status_code == 404

    async def test_regenerate_slide_regen_limit(self, setup_test_db):
        """Hitting regen limit returns 429."""
        from bot.services.team_store import create_team
        from bot.services.drafts_store import save_draft

        team = await create_team("T", creator_telegram_id=12345)
        draft = await save_draft(
            kind="carousel", topic="t", source="ai",
            payload={"slides": [{"heading": "S1"}], "regen_count": 5},
            team_id=team.team_id, created_by=12345,
        )
        client = _client()
        with patch("bot.handlers.monitor.notify_owner_throttled"):
            resp = client.post(
                f"/api/carousel/{draft.draft_id}/slides/0/regenerate",
                json={},
                headers=HEADERS,
            )
        assert resp.status_code == 429
        assert resp.json()["detail"]["error"] == "regen_limit"


# ---------------------------------------------------------------------------
# POST /api/carousel/{id}/slides/{idx}/versions/{v}/select
# ---------------------------------------------------------------------------

class TestSelectVersion:
    async def test_select_version_success(self, carousel_draft):
        _, draft = carousel_draft
        client = _client()
        with patch(
            "miniapp.api.routers.carousel.select_carousel_slide_version",
            new_callable=AsyncMock, return_value={"slides": []},
        ):
            resp = client.post(
                f"/api/carousel/{draft.draft_id}/slides/0/versions/0/select",
                headers=HEADERS,
            )
        assert resp.status_code == 200

    async def test_select_version_not_found(self, carousel_draft):
        _, draft = carousel_draft
        client = _client()
        with patch(
            "miniapp.api.routers.carousel.select_carousel_slide_version",
            new_callable=AsyncMock, return_value=None,
        ):
            resp = client.post(
                f"/api/carousel/{draft.draft_id}/slides/0/versions/99/select",
                headers=HEADERS,
            )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "carousel_version_not_found"


# ---------------------------------------------------------------------------
# DELETE /api/carousel/{id}/slides/{idx}/versions/{v}
# ---------------------------------------------------------------------------

class TestDeleteVersion:
    async def test_delete_version_success(self, carousel_draft):
        _, draft = carousel_draft
        client = _client()
        with patch(
            "miniapp.api.routers.carousel.delete_carousel_slide_version",
            new_callable=AsyncMock, return_value={"slides": []},
        ):
            resp = client.delete(
                f"/api/carousel/{draft.draft_id}/slides/0/versions/0",
                headers=HEADERS,
            )
        assert resp.status_code == 200

    async def test_delete_version_not_found(self, carousel_draft):
        _, draft = carousel_draft
        client = _client()
        with patch(
            "miniapp.api.routers.carousel.delete_carousel_slide_version",
            new_callable=AsyncMock, return_value=None,
        ):
            resp = client.delete(
                f"/api/carousel/{draft.draft_id}/slides/0/versions/99",
                headers=HEADERS,
            )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "carousel_version_not_found"


# ---------------------------------------------------------------------------
# POST /api/carousel/{id}/layout
# ---------------------------------------------------------------------------

class TestChangeLayout:
    async def test_change_layout_overlay(self, carousel_draft):
        _, draft = carousel_draft
        client = _client()
        resp = client.post(
            f"/api/carousel/{draft.draft_id}/layout",
            json={"layout_style": "overlay"},
            headers=HEADERS,
        )
        assert resp.status_code == 200

    async def test_change_layout_editorial(self, carousel_draft):
        _, draft = carousel_draft
        client = _client()
        resp = client.post(
            f"/api/carousel/{draft.draft_id}/layout",
            json={"layout_style": "editorial"},
            headers=HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["payload"]["layout_style"] == "editorial"

    async def test_change_layout_invalid_falls_back_to_overlay(self, carousel_draft):
        _, draft = carousel_draft
        client = _client()
        resp = client.post(
            f"/api/carousel/{draft.draft_id}/layout",
            json={"layout_style": "invalid_style"},
            headers=HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["payload"]["layout_style"] == "overlay"

    async def test_change_layout_not_found(self, setup_test_db):
        client = _client()
        resp = client.post(
            "/api/carousel/nonexistent/layout",
            json={"layout_style": "overlay"},
            headers=HEADERS,
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/carousel/{id}/regenerate-all
# ---------------------------------------------------------------------------

class TestRegenerateAll:
    async def test_regenerate_all_success(self, carousel_draft):
        _, draft = carousel_draft
        client = _client()
        with (
            patch("miniapp.api.routers.carousel.complete_carousel_regenerate_all", new_callable=AsyncMock),
            patch("miniapp.api.routers.carousel.set_generation_state", new_callable=AsyncMock),
        ):
            resp = client.post(
                f"/api/carousel/{draft.draft_id}/regenerate-all",
                headers=HEADERS,
            )
        assert resp.status_code == 200

    async def test_regenerate_all_not_found(self, setup_test_db):
        client = _client()
        resp = client.post(
            "/api/carousel/nonexistent/regenerate-all",
            headers=HEADERS,
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/carousel/{id}/slides/{idx}/preview
# ---------------------------------------------------------------------------

class TestSlidePreview:
    async def test_preview_success(self, carousel_draft):
        _, draft = carousel_draft
        client = _client()
        with patch(
            "bot.agents.carousel_preview_agent.generate_slide_preview",
            new_callable=AsyncMock, return_value=b"\x89PNG fake",
        ):
            resp = client.get(
                f"/api/carousel/{draft.draft_id}/slides/0/preview",
                headers=HEADERS,
            )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"

    async def test_preview_not_found(self, setup_test_db):
        client = _client()
        resp = client.get(
            "/api/carousel/nonexistent/slides/0/preview",
            headers=HEADERS,
        )
        assert resp.status_code == 404

    async def test_preview_generation_error(self, carousel_draft):
        _, draft = carousel_draft
        client = _client()
        with patch(
            "bot.agents.carousel_preview_agent.generate_slide_preview",
            new_callable=AsyncMock, side_effect=ValueError("No image"),
        ):
            resp = client.get(
                f"/api/carousel/{draft.draft_id}/slides/0/preview",
                headers=HEADERS,
            )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "slide_preview_failed"


# ---------------------------------------------------------------------------
# POST /api/carousel/{id}/preview
# ---------------------------------------------------------------------------

class TestPreviewAll:
    async def test_preview_all_success(self, carousel_draft):
        _, draft = carousel_draft
        client = _client()
        with patch(
            "bot.agents.carousel_preview_agent.generate_all_previews",
            new_callable=AsyncMock,
        ):
            resp = client.post(
                f"/api/carousel/{draft.draft_id}/preview",
                headers=HEADERS,
            )
        assert resp.status_code == 200

    async def test_preview_all_not_found(self, setup_test_db):
        client = _client()
        resp = client.post(
            "/api/carousel/nonexistent/preview",
            headers=HEADERS,
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/carousel/{id}/pptx
# ---------------------------------------------------------------------------

class TestPptxExport:
    async def test_pptx_export_overlay(self, carousel_draft):
        _, draft = carousel_draft
        client = _client()
        with (
            patch(
                "miniapp.api.routers.carousel.load_carousel_slide_images",
                return_value=[b"\x89PNG1", b"\x89PNG2"],
            ),
            patch(
                "miniapp.api.routers.carousel._build_pptx",
                return_value=b"PK\x03\x04fake_pptx",
            ),
        ):
            resp = client.get(
                f"/api/carousel/{draft.draft_id}/pptx",
                headers=HEADERS,
            )
        assert resp.status_code == 200
        assert "pptx" in resp.headers["content-type"] or "presentationml" in resp.headers["content-type"]

    async def test_pptx_export_not_found(self, setup_test_db):
        client = _client()
        resp = client.get("/api/carousel/nonexistent/pptx", headers=HEADERS)
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/carousel/{id}/pptx/import
# ---------------------------------------------------------------------------

class TestPptxImport:
    async def test_pptx_import_not_found(self, setup_test_db):
        client = _client()
        resp = client.post(
            "/api/carousel/nonexistent/pptx/import",
            files={"file": ("test.pptx", b"fakecontent", "application/octet-stream")},
            headers=HEADERS,
        )
        assert resp.status_code == 404

    async def test_pptx_import_empty_file(self, carousel_draft):
        _, draft = carousel_draft
        client = _client()
        resp = client.post(
            f"/api/carousel/{draft.draft_id}/pptx/import",
            files={"file": ("test.pptx", b"", "application/octet-stream")},
            headers=HEADERS,
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "empty_file"

    async def test_pptx_import_no_images(self, carousel_draft):
        _, draft = carousel_draft
        client = _client()
        with patch(
            "miniapp.api.routers.carousel.extract_images_from_pptx",
            return_value=[],
        ):
            resp = client.post(
                f"/api/carousel/{draft.draft_id}/pptx/import",
                files={"file": ("test.pptx", b"fakecontent", "application/octet-stream")},
                headers=HEADERS,
            )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "no_images_found_in_pptx"

    async def test_pptx_import_success(self, carousel_draft):
        _, draft = carousel_draft
        client = _client()
        with (
            patch(
                "miniapp.api.routers.carousel.extract_images_from_pptx",
                return_value=[b"\x89PNG1", b"\x89PNG2"],
            ),
            patch(
                "miniapp.api.routers.carousel.save_carousel_slide_asset",
                return_value={"path": "new.png", "prompt": "import"},
            ),
            patch(
                "miniapp.api.routers.carousel.create_revision",
                new_callable=AsyncMock,
            ),
        ):
            resp = client.post(
                f"/api/carousel/{draft.draft_id}/pptx/import",
                files={"file": ("test.pptx", b"fakecontent", "application/octet-stream")},
                headers=HEADERS,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["draft_id"] == draft.draft_id


# ---------------------------------------------------------------------------
# GET /api/carousel/{id}/canva/status
# ---------------------------------------------------------------------------

class TestCanvaStatus:
    async def test_canva_status_connected(self, carousel_draft):
        _, draft = carousel_draft
        mock_token = MagicMock()
        mock_token.access_token = "valid_token"
        client = _client()
        with patch(
            "bot.services.mentions_store.get_token",
            new_callable=AsyncMock, return_value=mock_token,
        ):
            resp = client.get(
                f"/api/carousel/{draft.draft_id}/canva/status",
                headers=HEADERS,
            )
        assert resp.status_code == 200
        assert resp.json()["connected"] is True

    async def test_canva_status_not_connected(self, carousel_draft):
        _, draft = carousel_draft
        client = _client()
        with patch(
            "bot.services.mentions_store.get_token",
            new_callable=AsyncMock, return_value=None,
        ):
            resp = client.get(
                f"/api/carousel/{draft.draft_id}/canva/status",
                headers=HEADERS,
            )
        assert resp.status_code == 200
        assert resp.json()["connected"] is False


# ---------------------------------------------------------------------------
# GET /api/carousel/{id}/canva/task-status
# ---------------------------------------------------------------------------

class TestCanvaTaskStatus:
    async def test_task_status_idle(self, carousel_draft):
        _, draft = carousel_draft
        client = _client()
        with (
            patch("bot.services.canva_task_worker._status_key", side_effect=lambda did, tt: f"{did}:{tt}"),
            patch("bot.services.canva_task_worker.live_status", {}),
            patch(
                "bot.services.video_task_store.get_active_task_for_draft",
                new_callable=AsyncMock, return_value=None,
            ),
        ):
            resp = client.get(
                f"/api/carousel/{draft.draft_id}/canva/task-status",
                headers=HEADERS,
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "idle"

    async def test_task_status_from_live(self, carousel_draft):
        _, draft = carousel_draft
        client = _client()
        live = {
            f"{draft.draft_id}:canva_export": {
                "status": "running", "step": "uploading",
            },
        }
        with (
            patch("bot.services.canva_task_worker._status_key", side_effect=lambda did, tt: f"{did}:{tt}"),
            patch("bot.services.canva_task_worker.live_status", live),
        ):
            resp = client.get(
                f"/api/carousel/{draft.draft_id}/canva/task-status",
                headers=HEADERS,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "running"
        assert data["step"] == "uploading"


# ---------------------------------------------------------------------------
# GET /api/carousel/{id}/canva/designs
# ---------------------------------------------------------------------------

class TestCanvaDesigns:
    async def test_canva_designs_success(self, carousel_draft):
        _, draft = carousel_draft
        client = _client()
        with patch(
            "bot.services.canva_api.list_canva_designs",
            new_callable=AsyncMock, return_value=[{"id": "d1", "title": "Design 1"}],
        ):
            resp = client.get(
                f"/api/carousel/{draft.draft_id}/canva/designs",
                headers=HEADERS,
            )
        assert resp.status_code == 200
        assert len(resp.json()["designs"]) == 1

    async def test_canva_designs_api_error(self, carousel_draft):
        _, draft = carousel_draft
        client = _client()
        from bot.services.canva_api import CanvaAPIError
        with patch(
            "bot.services.canva_api.list_canva_designs",
            new_callable=AsyncMock, side_effect=CanvaAPIError("fail"),
        ):
            resp = client.get(
                f"/api/carousel/{draft.draft_id}/canva/designs",
                headers=HEADERS,
            )
        assert resp.status_code == 502
        assert resp.json()["detail"] == "canva_list_failed"


# ---------------------------------------------------------------------------
# POST /api/carousel/{id}/canva/import
# ---------------------------------------------------------------------------

class TestCanvaImport:
    async def test_canva_import_not_found(self, setup_test_db):
        client = _client()
        resp = client.post(
            "/api/carousel/nonexistent/canva/import",
            json={"design_id": "abc"},
            headers=HEADERS,
        )
        assert resp.status_code == 404

    async def test_canva_import_success(self, carousel_draft):
        _, draft = carousel_draft
        client = _client()
        mock_task = MagicMock()
        mock_task.task_id = "task-1"
        with (
            patch(
                "bot.services.video_task_store.get_active_task_for_draft",
                new_callable=AsyncMock, return_value=None,
            ),
            patch(
                "bot.services.video_task_store.enqueue_task",
                new_callable=AsyncMock, return_value=mock_task,
            ),
            patch("bot.services.canva_task_worker._status_key", side_effect=lambda did, tt: f"{did}:{tt}"),
            patch("bot.services.canva_task_worker.live_status", {}),
        ):
            resp = client.post(
                f"/api/carousel/{draft.draft_id}/canva/import",
                json={"design_id": "canva-design-123"},
                headers=HEADERS,
            )
        assert resp.status_code == 202
        data = resp.json()
        assert data["task_id"] == "task-1"
        assert data["status"] == "pending"

    async def test_canva_import_already_running(self, carousel_draft):
        _, draft = carousel_draft
        client = _client()
        mock_task = MagicMock()
        mock_task.task_id = "existing-task"
        with patch(
            "bot.services.video_task_store.get_active_task_for_draft",
            new_callable=AsyncMock, return_value=mock_task,
        ):
            resp = client.post(
                f"/api/carousel/{draft.draft_id}/canva/import",
                json={"design_id": "abc"},
                headers=HEADERS,
            )
        assert resp.status_code == 409
        assert resp.json()["detail"] == "canva_import_already_running"


# ---------------------------------------------------------------------------
# POST /api/carousel/{id}/canva/export
# ---------------------------------------------------------------------------

class TestCanvaExport:
    async def test_canva_export_not_found(self, setup_test_db):
        client = _client()
        resp = client.post(
            "/api/carousel/nonexistent/canva/export",
            headers=HEADERS,
        )
        assert resp.status_code == 404

    async def test_canva_export_already_running(self, carousel_draft):
        _, draft = carousel_draft
        client = _client()
        mock_task = MagicMock()
        mock_task.task_id = "existing-task"
        with patch(
            "bot.services.video_task_store.get_active_task_for_draft",
            new_callable=AsyncMock, return_value=mock_task,
        ):
            resp = client.post(
                f"/api/carousel/{draft.draft_id}/canva/export",
                headers=HEADERS,
            )
        assert resp.status_code == 409
        assert resp.json()["detail"] == "canva_export_already_running"


# ---------------------------------------------------------------------------
# _load_brand_avatar helper
# ---------------------------------------------------------------------------

class TestLoadBrandAvatar:
    def test_load_avatar_no_path(self):
        from miniapp.api.routers.carousel import _load_brand_avatar
        assert _load_brand_avatar({}) is None

    def test_load_avatar_missing_file(self):
        from miniapp.api.routers.carousel import _load_brand_avatar
        assert _load_brand_avatar({"brand_avatar_path": "/nonexistent/file.png"}) is None


# ---------------------------------------------------------------------------
# Auth enforcement
# ---------------------------------------------------------------------------

class TestAuthEnforcement:
    async def test_no_auth_header_returns_403(self, carousel_draft, monkeypatch):
        monkeypatch.delenv("AROMA_BYPASS_AUTH", raising=False)
        _, draft = carousel_draft
        from miniapp_server import app
        client = TestClient(app)
        resp = client.get(f"/api/carousel/{draft.draft_id}")
        assert resp.status_code == 403
