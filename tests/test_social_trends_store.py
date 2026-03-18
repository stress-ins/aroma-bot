"""Tests for social_trends_store: CRUD, analytics queries, quota tracking."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from bot.services.social_trends_store import (
    check_hashtag_quota,
    cleanup_old_posts,
    get_best_posting_times,
    get_content_length_breakdown,
    get_format_breakdown,
    get_hashtag_stats,
    get_posting_heatmap,
    get_top_posts,
    list_social_posts,
    list_teams_with_social_accounts,
    record_hashtag_search,
    upsert_social_post,
)

TEAM = "team-test-001"


async def _seed_post(
    team_id: str = TEAM,
    platform: str = "instagram",
    post_id: str = "p1",
    *,
    text: str = "hello #test",
    hashtags: list[str] | None = None,
    like_count: int = 10,
    comment_count: int = 2,
    share_count: int = 0,
    reply_count: int = 0,
    media_type: str = "IMAGE",
    posted_at: datetime | None = None,
    author_username: str = "user1",
):
    await upsert_social_post(
        team_id=team_id,
        platform=platform,
        post_id=post_id,
        source_type="account",
        source_value=f"@{author_username}",
        author_username=author_username,
        text=text,
        hashtags=hashtags or ["test"],
        like_count=like_count,
        comment_count=comment_count,
        share_count=share_count,
        reply_count=reply_count,
        media_type=media_type,
        posted_at=posted_at or datetime.now(timezone.utc),
    )


class TestUpsert:
    async def test_insert_new_post(self):
        await _seed_post(post_id="new1")
        posts = await list_social_posts(TEAM, "instagram")
        assert len(posts) == 1
        assert posts[0]["post_id"] == "new1"
        assert posts[0]["like_count"] == 10

    async def test_upsert_updates_metrics(self):
        await _seed_post(post_id="upd1", like_count=5)
        await _seed_post(post_id="upd1", like_count=50)
        posts = await list_social_posts(TEAM, "instagram")
        assert len(posts) == 1
        assert posts[0]["like_count"] == 50

    async def test_team_isolation(self):
        await _seed_post(team_id="team-a", post_id="a1")
        await _seed_post(team_id="team-b", post_id="b1")
        a_posts = await list_social_posts("team-a", "instagram")
        b_posts = await list_social_posts("team-b", "instagram")
        assert len(a_posts) == 1
        assert len(b_posts) == 1
        assert a_posts[0]["post_id"] == "a1"
        assert b_posts[0]["post_id"] == "b1"


class TestTopPosts:
    async def test_ranked_by_engagement(self):
        await _seed_post(post_id="low", like_count=1, comment_count=0)
        await _seed_post(post_id="high", like_count=100, comment_count=50)
        await _seed_post(post_id="mid", like_count=20, comment_count=5)
        top = await get_top_posts(TEAM, "instagram", period_days=7, limit=2)
        assert len(top) == 2
        assert top[0]["post_id"] == "high"
        assert top[1]["post_id"] == "mid"


class TestHeatmap:
    async def test_heatmap_structure(self):
        now = datetime.now(timezone.utc)
        await _seed_post(post_id="hm1", posted_at=now)
        await _seed_post(post_id="hm2", posted_at=now)
        heatmap = await get_posting_heatmap(TEAM, "instagram", period_days=7)
        weekday = now.weekday()
        hour = now.hour
        assert weekday in heatmap
        assert hour in heatmap[weekday]
        assert heatmap[weekday][hour] == 2


class TestHashtagStats:
    async def test_hashtag_frequency(self):
        await _seed_post(post_id="hs1", hashtags=["wellness", "aroma"])
        await _seed_post(post_id="hs2", hashtags=["wellness", "oils"])
        await _seed_post(post_id="hs3", hashtags=["aroma"])
        stats = await get_hashtag_stats(TEAM, "instagram", period_days=7)
        tag_map = {s["tag"]: s["count"] for s in stats}
        assert tag_map["wellness"] == 2
        assert tag_map["aroma"] == 2
        assert tag_map["oils"] == 1


class TestFormatBreakdown:
    async def test_counts_per_type(self):
        await _seed_post(post_id="f1", media_type="IMAGE")
        await _seed_post(post_id="f2", media_type="IMAGE")
        await _seed_post(post_id="f3", media_type="VIDEO")
        breakdown = await get_format_breakdown(TEAM, "instagram")
        assert breakdown["IMAGE"] == 2
        assert breakdown["VIDEO"] == 1


class TestContentLength:
    async def test_length_buckets(self):
        await _seed_post(post_id="cl1", text="short")
        await _seed_post(post_id="cl2", text="m" * 150)
        await _seed_post(post_id="cl3", text="l" * 400)
        breakdown = await get_content_length_breakdown(TEAM)
        assert breakdown["short"] == 1
        assert breakdown["medium"] == 1
        assert breakdown["long"] == 1


class TestBestTimes:
    async def test_returns_hours(self):
        now = datetime.now(timezone.utc)
        await _seed_post(post_id="bt1", posted_at=now, like_count=50)
        await _seed_post(post_id="bt2", posted_at=now, like_count=30)
        times = await get_best_posting_times(TEAM, "instagram")
        assert len(times) >= 1
        assert times[0]["hour"] == now.hour
        assert times[0]["post_count"] == 2


class TestHashtagQuota:
    async def test_quota_tracking(self):
        used, remaining = await check_hashtag_quota(TEAM)
        assert used == 0
        assert remaining == 30

        await record_hashtag_search(TEAM, "wellness")
        await record_hashtag_search(TEAM, "aroma")
        await record_hashtag_search(TEAM, "wellness")  # duplicate tag

        used, remaining = await check_hashtag_quota(TEAM)
        assert used == 2  # unique count
        assert remaining == 28


class TestCleanup:
    async def test_deletes_old_posts(self):
        old = datetime.now(timezone.utc) - timedelta(days=100)
        recent = datetime.now(timezone.utc) - timedelta(days=1)
        await _seed_post(post_id="old1", posted_at=old)
        await _seed_post(post_id="new1", posted_at=recent)
        deleted = await cleanup_old_posts(days=90)
        assert deleted == 1
        posts = await list_social_posts(TEAM, "instagram")
        assert len(posts) == 1
        assert posts[0]["post_id"] == "new1"


class TestListTeams:
    async def test_returns_teams_with_accounts(self):
        from bot.services.brand_settings_store import get_brand_settings, update_brand_settings
        from bot.services.team_store import create_team

        team = await create_team("Trends Team", creator_telegram_id=9999)
        await get_brand_settings(team.team_id)  # ensure row exists
        await update_brand_settings(
            team.team_id,
            instagram_accounts=[{"username": "competitor1"}],
        )
        teams = await list_teams_with_social_accounts()
        found = [t for t in teams if t["team_id"] == team.team_id]
        assert len(found) == 1
        assert found[0]["has_ig"] is True
        assert found[0]["has_threads"] is False
