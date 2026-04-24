"""Tests for blend constructor router — blend-of-week endpoint."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _bypass_auth(monkeypatch):
    monkeypatch.setenv("AROMA_BYPASS_AUTH", "1")


HEADERS = {
    "X-Telegram-Init-Data": "user=%7B%22id%22%3A12345%7D&auth_date=9999999999&hash=abc",
}


class TestBlendOfWeek:
    async def test_blend_of_week_creates_two_drafts(self, setup_test_db):
        from bot.services.team_store import create_team
        team = await create_team("Blend Test", creator_telegram_id=12345)

        from miniapp_server import app

        # Patch BackgroundTasks.add_task to prevent actual generation
        bg_tasks = []
        original_add_task = None

        def capture_tasks(self, func, *args, **kwargs):
            bg_tasks.append((func.__name__, args, kwargs))

        with patch("fastapi.BackgroundTasks.add_task", capture_tasks):
            client = TestClient(app)
            resp = client.post(
                "/api/blend-constructor/blend-of-week",
                json={
                    "title": "Утренний тонус",
                    "brief": "бодрость",
                    "oils": [
                        {"name_ru": "Лимон", "name_en": "Lemon", "drops": 3, "role": "основа"},
                        {"name_ru": "Мята", "name_en": "Peppermint", "drops": 2, "role": "акцент"},
                    ],
                    "total_drops": 5,
                    "profile": {"focus": 40, "energy": 35, "creativity": 15, "calm": 10},
                    "expert_note": "Лимон и мята дают бодрость",
                    "application_guide": "В диффузор",
                    "tags": ["утро"],
                },
                headers={**HEADERS, "X-Team-Id": team.team_id},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "carousel_draft_id" in data
        assert "content_draft_id" in data
        assert "topic" in data
        assert "Утренний тонус" in data["topic"]

        # Verify both drafts exist
        from bot.services.drafts_store import get_draft
        carousel = await get_draft(data["carousel_draft_id"])
        content = await get_draft(data["content_draft_id"])
        assert carousel is not None
        assert content is not None
        assert carousel.kind == "carousel"
        assert content.kind == "instagram"

        # Verify background tasks were scheduled
        assert len(bg_tasks) == 2
        task_names = {t[0] for t in bg_tasks}
        assert "complete_carousel_generation" in task_names
        assert "complete_content_generation" in task_names

    async def test_blend_of_week_carousel_payload_has_mood_defaults(self, setup_test_db):
        """Carousel draft created from blend-of-week must persist goal_key/emotion defaults
        in payload — same shape as direct /api/generate/carousel call."""
        from bot.services.team_store import create_team
        team = await create_team("Mood Defaults", creator_telegram_id=12345)

        from miniapp_server import app

        bg_tasks: list[tuple[str, tuple, dict]] = []

        def capture_tasks(self, func, *args, **kwargs):
            bg_tasks.append((func.__name__, args, kwargs))

        with patch("fastapi.BackgroundTasks.add_task", capture_tasks):
            client = TestClient(app)
            resp = client.post(
                "/api/blend-constructor/blend-of-week",
                json={
                    "title": "Утро",
                    "brief": "тонус",
                    "oils": [{"name_ru": "Лимон", "name_en": "Lemon", "drops": 3, "role": "основа"}],
                    "total_drops": 3,
                    "profile": {"focus": 50, "energy": 30, "creativity": 10, "calm": 10},
                    "expert_note": "ok",
                    "application_guide": "В диффузор",
                    "tags": ["утро"],
                },
                headers={**HEADERS, "X-Team-Id": team.team_id},
            )
        assert resp.status_code == 200
        carousel_draft_id = resp.json()["carousel_draft_id"]

        from bot.services.drafts_store import get_draft
        carousel = await get_draft(carousel_draft_id)
        assert carousel is not None
        assert carousel.payload.get("goal_key") == "trust"
        assert carousel.payload.get("emotion") == "calm"

        # And the background task call must mirror those values via kwargs
        carousel_call = next(t for t in bg_tasks if t[0] == "complete_carousel_generation")
        kwargs = carousel_call[2]
        assert kwargs.get("goal_key") == "trust"
        assert kwargs.get("emotion") == "calm"
