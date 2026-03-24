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


    async def test_suggestions_include_insights(self, _seed_team_and_posts):
        team = _seed_team_and_posts
        from miniapp_server import app
        client = TestClient(app)
        resp = client.get(
            "/api/trends/suggestions?platform=instagram",
            headers={**HEADERS, "X-Team-Id": team.team_id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "insights" in data
        insights = data["insights"]
        assert len(insights) > 0
        ins = insights[0]
        assert "topic" in ins
        assert "engagement_score" in ins
        assert isinstance(ins["engagement_score"], int)
        assert "author_username" in ins
        assert "suggested_format" in ins
        assert ins["suggested_format"] in ("carousel", "reels", "threads_series", "content")
        assert "hashtags" in ins

    async def test_suggestions_threads_insights(self, _seed_team_and_posts):
        team = _seed_team_and_posts
        from miniapp_server import app
        client = TestClient(app)
        resp = client.get(
            "/api/trends/suggestions?platform=threads",
            headers={**HEADERS, "X-Team-Id": team.team_id},
        )
        assert resp.status_code == 200
        data = resp.json()
        insights = data.get("insights", [])
        assert len(insights) > 0
        # Threads posts should suggest threads_series format
        formats = {ins["suggested_format"] for ins in insights}
        assert "threads_series" in formats


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
            "/api/social/monitored-accounts/instagram",
            params={"username": "new_competitor"},
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


class TestTrackedHashtags:
    async def test_list_tracked_hashtags_empty(self, _seed_team_and_posts):
        team = _seed_team_and_posts
        from miniapp_server import app
        client = TestClient(app)
        resp = client.get(
            "/api/social/tracked-hashtags",
            headers={**HEADERS, "X-Team-Id": team.team_id},
        )
        assert resp.status_code == 200
        assert resp.json()["items"] == []

    async def test_add_and_remove_hashtag(self, _seed_team_and_posts):
        team = _seed_team_and_posts
        from miniapp_server import app
        client = TestClient(app)
        headers = {**HEADERS, "X-Team-Id": team.team_id}

        # Add
        resp = client.post(
            "/api/social/tracked-hashtags",
            json={"tag": "#ароматерапия"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert "ароматерапия" in resp.json()["items"]

        # Add another
        resp = client.post(
            "/api/social/tracked-hashtags",
            json={"tag": "эфирныемасла"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 2

        # Remove
        resp = client.delete(
            "/api/social/tracked-hashtags/ароматерапия",
            headers=headers,
        )
        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 1
        assert "эфирныемасла" in resp.json()["items"]

    async def test_duplicate_rejected(self, _seed_team_and_posts):
        team = _seed_team_and_posts
        from miniapp_server import app
        client = TestClient(app)
        headers = {**HEADERS, "X-Team-Id": team.team_id}

        client.post("/api/social/tracked-hashtags", json={"tag": "test"}, headers=headers)
        resp = client.post("/api/social/tracked-hashtags", json={"tag": "test"}, headers=headers)
        assert resp.status_code == 400
        assert resp.json()["detail"] == "already_tracked"


class TestAccountStats:
    async def test_account_stats(self, _seed_team_and_posts):
        team = _seed_team_and_posts
        from miniapp_server import app
        client = TestClient(app)
        resp = client.get(
            "/api/trends/account-stats",
            headers={**HEADERS, "X-Team-Id": team.team_id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "accounts" in data
        accounts = data["accounts"]
        assert len(accounts) >= 2  # ig + threads
        # Each has platform, source_value, post_count, last_collected
        for a in accounts:
            assert "platform" in a
            assert "post_count" in a
            assert a["post_count"] > 0
            assert "last_collected" in a


class TestRepostLeaders:
    async def test_threads_repost_leaders(self, _seed_team_and_posts):
        team = _seed_team_and_posts
        from miniapp_server import app
        client = TestClient(app)
        resp = client.get(
            "/api/trends/threads?period=7",
            headers={**HEADERS, "X-Team-Id": team.team_id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "repost_leaders" in data
        leaders = data["repost_leaders"]
        assert len(leaders) > 0
        # Should be sorted by share_count descending
        share_counts = [l.get("share_count", 0) for l in leaders]
        assert share_counts == sorted(share_counts, reverse=True)


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
