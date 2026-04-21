"""Tests for InstagramTrendsCollector — mock httpx responses."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from analytics.instagram_trends import InstagramTrendsCollector
from bot.services.social_trends_store import list_social_posts


def _ts(days_ago: int) -> str:
    """Return ISO timestamp `days_ago` days before now — keeps mock posts
    inside the 30-day collector window without timezone drift over time."""
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%S+0000")


def _mock_response(data: dict, status_code: int = 200) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        json=data,
        request=httpx.Request("GET", "https://graph.instagram.com/test"),
    )


TEAM = "team-ig-test"


class TestCollectFromAccounts:
    async def test_collects_posts_from_business_discovery(self):
        mock_data = {
            "business_discovery": {
                "username": "competitor1",
                "media": {
                    "data": [
                        {
                            "id": "ig_post_1",
                            "media_type": "IMAGE",
                            "permalink": "https://instagram.com/p/1",
                            "caption": "Great #wellness post about #aroma therapy",
                            "like_count": 42,
                            "comments_count": 5,
                            "timestamp": _ts(1),
                        },
                        {
                            "id": "ig_post_2",
                            "media_type": "VIDEO",
                            "permalink": "https://instagram.com/p/2",
                            "caption": "Another post",
                            "like_count": 10,
                            "comments_count": 1,
                            "timestamp": _ts(2),
                        },
                    ]
                },
            }
        }

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _mock_response(mock_data)

            collector = InstagramTrendsCollector(TEAM, "token123", "user123")
            count = await collector.collect_from_accounts([
                {"username": "competitor1"},
            ])

        assert count == 2
        posts = await list_social_posts(TEAM, "instagram")
        assert len(posts) == 2
        post1 = next(p for p in posts if p["post_id"] == "ig_post_1")
        assert post1["like_count"] == 42
        assert "wellness" in post1["hashtags"]
        assert "aroma" in post1["hashtags"]

    async def test_skips_empty_accounts(self):
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            collector = InstagramTrendsCollector(TEAM, "tok", "uid")
            count = await collector.collect_from_accounts([
                {"username": ""},
                {},
            ])
        assert count == 0
        mock_get.assert_not_called()


class TestCollectFromHashtags:
    async def test_collects_hashtag_posts(self):
        search_resp = _mock_response({"data": [{"id": "ht_123"}]})
        media_resp = _mock_response({
            "data": [
                {
                    "id": "ht_post_1",
                    "media_type": "IMAGE",
                    "permalink": "https://instagram.com/p/ht1",
                    "caption": "Post with #wellness",
                    "like_count": 20,
                    "comments_count": 3,
                    "timestamp": _ts(1),
                }
            ]
        })

        call_count = 0

        async def mock_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            url = str(args[0]) if args else str(kwargs.get("url", ""))
            if "ig_hashtag_search" in url:
                return search_resp
            return media_resp

        with patch("httpx.AsyncClient.get", side_effect=mock_get):
            collector = InstagramTrendsCollector(TEAM, "tok", "uid")
            count = await collector.collect_from_hashtags(["wellness"])

        assert count >= 1  # top_media + recent_media
        posts = await list_social_posts(TEAM, "instagram")
        assert any(p["post_id"] == "ht_post_1" for p in posts)


class TestGetSummary:
    async def test_summary_structure(self):
        from bot.services.social_trends_store import upsert_social_post

        now = datetime.now(timezone.utc)
        for i in range(3):
            await upsert_social_post(
                team_id=TEAM,
                platform="instagram",
                post_id=f"sum_{i}",
                source_type="account",
                source_value="@test",
                like_count=10 * (i + 1),
                hashtags=["test"],
                posted_at=now,
            )

        collector = InstagramTrendsCollector(TEAM, "tok", "uid")
        summary = await collector.get_summary(period_days=7)

        assert summary["platform"] == "instagram"
        assert len(summary["top_posts"]) == 3
        assert isinstance(summary["avg_engagement"], (int, float))
        assert isinstance(summary["top_hashtags"], list)
        assert isinstance(summary["best_times"], list)
