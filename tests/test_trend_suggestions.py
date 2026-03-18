"""Tests for trend suggestions: plan prompt enrichment and API endpoint."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest


TEAM = "team-suggest-test"


@pytest.fixture()
async def _seed_trends(setup_test_db):
    from bot.services.team_store import create_team
    from bot.services.brand_settings_store import get_brand_settings
    from bot.services.social_trends_store import upsert_social_post

    team = await create_team("Suggest Team", creator_telegram_id=55555)
    await get_brand_settings(team.team_id)

    now = datetime.now(timezone.utc)
    for i in range(3):
        await upsert_social_post(
            team_id=team.team_id,
            platform="instagram",
            post_id=f"sug_ig_{i}",
            source_type="account",
            source_value="@competitor",
            text=f"Trending post about wellness topic {i}",
            hashtags=["wellness", "aroma"],
            like_count=50 * (i + 1),
            comment_count=5,
            posted_at=now,
        )
        await upsert_social_post(
            team_id=team.team_id,
            platform="threads",
            post_id=f"sug_th_{i}",
            source_type="account",
            source_value="@threads_comp",
            text=f"Great hook for thread {i}\nBody text follows here",
            like_count=30 * (i + 1),
            reply_count=10,
            posted_at=now,
        )

    return team


class TestBuildSocialTrendsText:
    async def test_builds_enrichment_text(self, _seed_trends):
        team = _seed_trends
        from miniapp.api.routers.plans import _build_social_trends_text

        text = await _build_social_trends_text(team.team_id)
        assert "Instagram" in text
        assert "Threads" in text
        assert "wellness" in text or "aroma" in text

    async def test_empty_for_no_data(self, setup_test_db):
        from miniapp.api.routers.plans import _build_social_trends_text

        text = await _build_social_trends_text("nonexistent-team")
        assert text == ""


class TestGeneratePlanSyncSignature:
    def test_accepts_social_trends_text(self):
        """Verify generate_plan_sync accepts the new parameter."""
        from bot.agents.planner import generate_plan_sync
        import inspect

        sig = inspect.signature(generate_plan_sync)
        assert "social_trends_text" in sig.parameters
        assert sig.parameters["social_trends_text"].default == ""


class TestSuggestionsApiEndpoint:
    async def test_suggestions_returns_data(self, _seed_trends):
        team = _seed_trends
        import os
        os.environ["AROMA_BYPASS_AUTH"] = "1"
        from miniapp_server import app
        from fastapi.testclient import TestClient

        client = TestClient(app)
        resp = client.get(
            "/api/trends/suggestions?platform=instagram",
            headers={
                "X-Telegram-Init-Data": "user=%7B%22id%22%3A55555%7D&auth_date=9999999999&hash=abc",
                "X-Team-Id": team.team_id,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["platform"] == "instagram"
        assert isinstance(data["trending_topics"], list)
        assert isinstance(data["trending_hashtags"], list)
        assert isinstance(data["best_times"], list)
