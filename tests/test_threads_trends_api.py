"""Tests for ThreadsTrendsCollector — mock httpx responses."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from analytics.threads_trends_api import ThreadsTrendsCollector
from bot.services.social_trends_store import list_social_posts


def _ts(days_ago: int) -> str:
    """Return ISO timestamp `days_ago` days before now — keeps mock posts
    inside the 30-day collector window without timezone drift over time."""
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%S+0000")


def _mock_response(data: dict, status_code: int = 200) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        json=data,
        request=httpx.Request("GET", "https://graph.threads.net/test"),
    )


TEAM = "team-threads-test"


class TestCollectFromAccounts:
    async def test_collects_threads(self):
        mock_data = {
            "data": [
                {
                    "id": "th_1",
                    "text": "First thread about wellness",
                    "timestamp": _ts(1),
                    "permalink": "https://threads.net/@user/post/1",
                    "username": "competitor1",
                    "media_type": "TEXT_POST",
                    "like_count": 25,
                    "reply_count": 8,
                    "repost_count": 3,
                    "quotes_count": 1,
                },
                {
                    "id": "th_2",
                    "text": "Second thread about aroma",
                    "timestamp": _ts(2),
                    "permalink": "https://threads.net/@user/post/2",
                    "username": "competitor1",
                    "media_type": "TEXT_POST",
                    "like_count": 10,
                    "reply_count": 2,
                    "repost_count": 0,
                    "quotes_count": 0,
                },
            ],
            "paging": {},
        }

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _mock_response(mock_data)

            collector = ThreadsTrendsCollector(TEAM, "token123", "uid123")
            count = await collector.collect_from_accounts([
                {"username": "competitor1", "threads_user_id": "uid456"},
            ])

        assert count == 2
        posts = await list_social_posts(TEAM, "threads")
        assert len(posts) == 2
        post1 = next(p for p in posts if p["post_id"] == "th_1")
        assert post1["like_count"] == 25
        assert post1["reply_count"] == 8
        assert post1["share_count"] == 3  # repost_count → share_count

    async def test_pagination(self):
        page1 = {
            "data": [
                {
                    "id": f"th_page1_{i}",
                    "text": f"Post {i}",
                    "timestamp": _ts(1),
                    "username": "user1",
                    "media_type": "TEXT_POST",
                    "like_count": 5,
                    "reply_count": 1,
                    "repost_count": 0,
                    "quotes_count": 0,
                }
                for i in range(5)
            ],
            "paging": {"next": "https://graph.threads.net/v1.0/next?cursor=abc"},
        }
        page2 = {
            "data": [
                {
                    "id": "th_page2_0",
                    "text": "Last post",
                    "timestamp": _ts(2),
                    "username": "user1",
                    "media_type": "TEXT_POST",
                    "like_count": 3,
                    "reply_count": 0,
                    "repost_count": 0,
                    "quotes_count": 0,
                }
            ],
            "paging": {},
        }

        call_count = 0

        async def mock_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_response(page1)
            return _mock_response(page2)

        with patch("httpx.AsyncClient.get", side_effect=mock_get):
            collector = ThreadsTrendsCollector(TEAM, "tok", "uid")
            count = await collector.collect_from_accounts([
                {"username": "user1", "threads_user_id": "ext_uid_1"},
            ])

        assert count == 6
        # 2 pages + 6 per-post insights enrichment calls
        assert call_count == 8


class TestOwnInsights:
    async def test_returns_metrics(self):
        mock_data = {
            "data": [
                {"name": "views", "total_value": {"value": 1200}},
                {"name": "likes", "total_value": {"value": 50}},
                {"name": "replies", "total_value": {"value": 12}},
            ]
        }

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _mock_response(mock_data)

            collector = ThreadsTrendsCollector(TEAM, "tok", "uid")
            insights = await collector.collect_own_insights()

        assert insights["views"] == 1200
        assert insights["likes"] == 50
        assert insights["replies"] == 12

    async def test_handles_api_error(self):
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _mock_response(
                {"error": {"message": "rate limited"}}, status_code=429
            )
            collector = ThreadsTrendsCollector(TEAM, "tok", "uid")
            insights = await collector.collect_own_insights()

        assert insights == {}


class TestGetSummary:
    async def test_summary_with_hooks(self):
        from bot.services.social_trends_store import upsert_social_post

        now = datetime.now(timezone.utc)
        await upsert_social_post(
            team_id=TEAM, platform="threads", post_id="hook1",
            source_type="account", source_value="@test",
            text="This hook grabs attention\nThen the body follows",
            like_count=100, reply_count=30, posted_at=now,
        )
        await upsert_social_post(
            team_id=TEAM, platform="threads", post_id="hook2",
            source_type="account", source_value="@test",
            text="Another great opening line\nMore content here",
            like_count=50, reply_count=10, posted_at=now,
        )

        collector = ThreadsTrendsCollector(TEAM, "tok", "uid")
        summary = await collector.get_summary(period_days=7)

        assert summary["platform"] == "threads"
        assert len(summary["thread_hooks"]) == 2
        assert "This hook grabs attention" in summary["thread_hooks"]
        assert isinstance(summary["avg_reply_rate"], (int, float))
