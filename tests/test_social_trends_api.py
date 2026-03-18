"""Tests for social trends API endpoints."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _bypass_auth(monkeypatch):
    monkeypatch.setenv("AROMA_BYPASS_AUTH", "1")


HEADERS = {
    "X-Telegram-Init-Data": "user=%7B%22id%22%3A12345%7D&auth_date=9999999999&hash=abc",
}


@pytest.fixture()
async def _seed_team_and_posts(setup_test_db):
    """Create a team, brand settings, and seed some posts."""
    from bot.services.team_store import create_team
    from bot.services.brand_settings_store import get_brand_settings, update_brand_settings
    from bot.services.social_trends_store import upsert_social_post

    team = await create_team("API Test Team", creator_telegram_id=12345)
    await get_brand_settings(team.team_id)
    await update_brand_settings(
        team.team_id,
        instagram_accounts=[{"username": "competitor1", "status": "available"}],
        threads_accounts=[{"username": "threads_user", "status": "available"}],
    )

    now = datetime.now(timezone.utc)
    for i in range(5):
        await upsert_social_post(
            team_id=team.team_id,
            platform="instagram",
            post_id=f"ig_{i}",
            source_type="account",
            source_value="@competitor1",
            author_username="competitor1",
            text=f"Post {i} about #wellness and #aroma",
            hashtags=["wellness", "aroma"],
            like_count=10 * (i + 1),
            comment_count=i,
            media_type="IMAGE" if i % 2 == 0 else "VIDEO",
            posted_at=now,
        )
        await upsert_social_post(
            team_id=team.team_id,
            platform="threads",
            post_id=f"th_{i}",
            source_type="account",
            source_value="@threads_user",
            author_username="threads_user",
            text=f"Thread hook line {i}\nBody text here about wellness",
            like_count=5 * (i + 1),
            reply_count=i * 2,
            share_count=i,
            media_type="TEXT_POST",
            posted_at=now,
        )

    return team


class TestInstagramEndpoint:
    async def test_get_instagram_trends(self, _seed_team_and_posts):
        team = _seed_team_and_posts
        from miniapp_server import app
        client = TestClient(app)
        resp = client.get(
            "/api/trends/instagram?period=7",
            headers={**HEADERS, "X-Team-Id": team.team_id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "top_posts" in data
        assert "hashtag_cloud" in data
        assert "heatmap" in data
        assert "format_breakdown" in data
        assert data["period_days"] == 7


class TestThreadsEndpoint:
    async def test_get_threads_trends(self, _seed_team_and_posts):
        team = _seed_team_and_posts
        from miniapp_server import app
        client = TestClient(app)
        resp = client.get(
            "/api/trends/threads?period=7",
            headers={**HEADERS, "X-Team-Id": team.team_id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "top_posts" in data
        assert "thread_hooks" in data
        assert "trending_keywords" in data
        assert "best_times" in data
        assert "avg_reply_rate" in data


class TestCompareEndpoint:
    async def test_cross_platform_compare(self, _seed_team_and_posts):
        team = _seed_team_and_posts
        from miniapp_server import app
        client = TestClient(app)
        resp = client.get(
            "/api/trends/compare?period=7",
            headers={**HEADERS, "X-Team-Id": team.team_id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "instagram" in data
        assert "threads" in data
        assert data["instagram"]["post_count"] > 0
        assert data["threads"]["post_count"] > 0


class TestSuggestionsEndpoint:
    async def test_suggestions_for_instagram(self, _seed_team_and_posts):
        team = _seed_team_and_posts
        from miniapp_server import app
        client = TestClient(app)
        resp = client.get(
            "/api/trends/suggestions?platform=instagram",
            headers={**HEADERS, "X-Team-Id": team.team_id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "trending_topics" in data
        assert "trending_hashtags" in data
        assert "best_times" in data
        assert data["platform"] == "instagram"


class TestMonitoredAccounts:
    async def test_list_monitored_accounts(self, _seed_team_and_posts):
        team = _seed_team_and_posts
        from miniapp_server import app
        client = TestClient(app)
        resp = client.get(
            "/api/social/monitored-accounts",
            headers={**HEADERS, "X-Team-Id": team.team_id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["instagram"]) == 1
        assert data["instagram"][0]["username"] == "competitor1"
        assert len(data["threads"]) == 1

    async def test_add_and_remove_account(self, _seed_team_and_posts):
        team = _seed_team_and_posts
        from miniapp_server import app
        client = TestClient(app)
        headers = {**HEADERS, "X-Team-Id": team.team_id}

        # Add
        resp = client.post(
            "/api/social/monitored-accounts",
            json={"platform": "instagram", "username": "@new_competitor"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 2

        # Remove
        resp = client.delete(
            "/api/social/monitored-accounts/instagram/new_competitor",
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["remaining"] == 1

    async def test_duplicate_rejected(self, _seed_team_and_posts):
        team = _seed_team_and_posts
        from miniapp_server import app
        client = TestClient(app)
        headers = {**HEADERS, "X-Team-Id": team.team_id}

        resp = client.post(
            "/api/social/monitored-accounts",
            json={"platform": "instagram", "username": "competitor1"},
            headers=headers,
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "already_monitored"


class TestRefreshEndpoint:
    async def test_refresh_returns_started(self, _seed_team_and_posts):
        team = _seed_team_and_posts
        from miniapp_server import app
        client = TestClient(app)
        resp = client.post(
            "/api/trends/refresh",
            headers={**HEADERS, "X-Team-Id": team.team_id},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "started"
