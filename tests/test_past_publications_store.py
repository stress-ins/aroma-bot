"""Tests for past_publications_store: CRUD, filtering, stats, bulk_create."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest


class TestPastPublicationsStore:
    async def test_create_and_get(self):
        from bot.services.past_publications_store import create_publication, get_publication

        pub = await create_publication(
            platform="threads",
            topic="Утренний ритуал",
            caption="Масло лаванды для утра",
            kind="text",
            likes=42,
            views=500,
        )
        assert pub.pub_id
        assert pub.platform == "threads"
        assert pub.topic == "Утренний ритуал"
        assert pub.likes == 42
        assert pub.views == 500
        assert pub.score_engagement is None

        fetched = await get_publication(pub.pub_id)
        assert fetched is not None
        assert fetched.pub_id == pub.pub_id
        assert fetched.caption == "Масло лаванды для утра"

    async def test_update(self):
        from bot.services.past_publications_store import create_publication, update_publication

        pub = await create_publication(platform="instagram", topic="Test")
        updated = await update_publication(pub.pub_id, score_engagement=4, score_brand_fit=3, notes="good post")
        assert updated is not None
        assert updated.score_engagement == 4
        assert updated.score_brand_fit == 3
        assert updated.notes == "good post"

    async def test_update_nonexistent(self):
        from bot.services.past_publications_store import update_publication

        result = await update_publication("nonexistent", score_engagement=5)
        assert result is None

    async def test_delete(self):
        from bot.services.past_publications_store import create_publication, delete_publication, get_publication

        pub = await create_publication(platform="telegram", topic="To delete")
        assert await delete_publication(pub.pub_id) is True
        assert await get_publication(pub.pub_id) is None
        assert await delete_publication(pub.pub_id) is False

    async def test_list_publications(self):
        from bot.services.past_publications_store import create_publication, list_publications

        team = "test-team-list"
        await create_publication(platform="threads", topic="A", team_id=team)
        await create_publication(platform="instagram", topic="B", team_id=team)
        await create_publication(platform="threads", topic="C", team_id=team)

        all_pubs = await list_publications(team)
        assert len(all_pubs) >= 3

        threads_only = await list_publications(team, platform="threads")
        assert all(p.platform == "threads" for p in threads_only)

    async def test_list_rated_unrated(self):
        from bot.services.past_publications_store import create_publication, update_publication, list_publications

        team = "test-team-rated"
        pub1 = await create_publication(platform="threads", topic="Rated", team_id=team)
        await create_publication(platform="threads", topic="Unrated", team_id=team)
        await update_publication(pub1.pub_id, score_engagement=5)

        rated = await list_publications(team, rated_only=True)
        assert all(p.score_engagement is not None for p in rated)

        unrated = await list_publications(team, unrated_only=True)
        assert all(p.score_engagement is None for p in unrated)

    async def test_find_by_external_id(self):
        from bot.services.past_publications_store import create_publication, find_by_external_id

        await create_publication(platform="threads", external_id="ext123", topic="Ext test")
        found = await find_by_external_id("threads", "ext123")
        assert found is not None
        assert found.external_id == "ext123"

        not_found = await find_by_external_id("threads", "nonexistent")
        assert not_found is None

    async def test_avg_score(self):
        from bot.services.past_publications_store import create_publication, update_publication

        pub = await create_publication(platform="threads", topic="Score test")
        updated = await update_publication(
            pub.pub_id,
            score_engagement=4, score_brand_fit=3, score_craft=5, score_goal_hit=4,
        )
        assert updated is not None
        assert updated.avg_score == 4.0

    async def test_avg_score_partial(self):
        from bot.services.past_publications_store import create_publication, update_publication

        pub = await create_publication(platform="threads", topic="Partial score")
        updated = await update_publication(pub.pub_id, score_engagement=3)
        assert updated is not None
        assert updated.avg_score == 3.0

    async def test_avg_score_none(self):
        from bot.services.past_publications_store import create_publication

        pub = await create_publication(platform="threads", topic="No score")
        assert pub.avg_score is None

    async def test_get_stats(self):
        from bot.services.past_publications_store import create_publication, update_publication, get_stats

        team = "test-team-stats"
        pub1 = await create_publication(platform="threads", topic="S1", team_id=team)
        pub2 = await create_publication(platform="instagram", topic="S2", team_id=team)
        await update_publication(pub1.pub_id, score_engagement=4, score_brand_fit=4, score_craft=4, score_goal_hit=4)
        await update_publication(pub2.pub_id, score_engagement=2, score_brand_fit=2, score_craft=2, score_goal_hit=2)

        stats = await get_stats(team)
        assert stats["total"] >= 2
        assert stats["rated"] >= 2
        assert stats["avg_score"] is not None
        assert stats["avg_score"] == 3.0

    async def test_bulk_create_dedup(self):
        from bot.services.past_publications_store import bulk_create, find_by_external_id

        pubs = [
            {"platform": "threads", "external_id": "bulk1", "topic": "Bulk A"},
            {"platform": "threads", "external_id": "bulk2", "topic": "Bulk B"},
        ]
        result = await bulk_create(pubs, team_id="test-team-bulk")
        assert result["imported"] == 2
        assert result["skipped"] == 0

        # Running again should skip all
        result2 = await bulk_create(pubs, team_id="test-team-bulk")
        assert result2["imported"] == 0
        assert result2["skipped"] == 2

    async def test_to_dict(self):
        from bot.services.past_publications_store import create_publication, update_publication

        pub = await create_publication(platform="threads", topic="Dict test")
        await update_publication(pub.pub_id, score_engagement=5, score_craft=3)
        from bot.services.past_publications_store import get_publication
        fetched = await get_publication(pub.pub_id)
        d = fetched.to_dict()
        assert d["pub_id"] == pub.pub_id
        assert d["avg_score"] == 4.0
        assert "platform" in d

    async def test_published_at(self):
        from bot.services.past_publications_store import create_publication

        dt = datetime(2026, 3, 15, 10, 0, 0, tzinfo=timezone.utc)
        pub = await create_publication(platform="instagram", topic="With date", published_at=dt)
        assert pub.published_at is not None
        assert "2026-03-15" in pub.published_at
