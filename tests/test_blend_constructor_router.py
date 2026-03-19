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
