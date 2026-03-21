"""Tests for content_analytics: format/pillar performance, top publications, prompt text."""
from __future__ import annotations

import pytest


TEAM = "team-analytics-test"


async def _seed_publications(team_id: str = TEAM):
    from bot.services.past_publications_store import create_publication, update_publication
    from datetime import datetime, timezone

    pub1 = await create_publication(
        platform="threads", kind="text", topic="Morning ritual",
        team_id=team_id, likes=100, views=1000,
        published_at=datetime(2026, 3, 10, tzinfo=timezone.utc),
        content_pillar="Образование",
    )
    await update_publication(pub1.pub_id, score_engagement=5, score_brand_fit=4, score_craft=5, score_goal_hit=4)

    pub2 = await create_publication(
        platform="instagram", kind="carousel", topic="Top 5 oils",
        team_id=team_id, likes=200, views=2000,
        published_at=datetime(2026, 3, 12, tzinfo=timezone.utc),
        content_pillar="Рецепты",
    )
    await update_publication(pub2.pub_id, score_engagement=3, score_brand_fit=3, score_craft=3, score_goal_hit=3)

    pub3 = await create_publication(
        platform="threads", kind="text", topic="Evening relaxation",
        team_id=team_id, likes=80, views=800,
        published_at=datetime(2026, 3, 14, tzinfo=timezone.utc),
        content_pillar="Образование",
    )
    await update_publication(pub3.pub_id, score_engagement=4, score_brand_fit=4, score_craft=4, score_goal_hit=4)

    # Unrated publication
    await create_publication(
        platform="telegram", kind="text", topic="Unrated post",
        team_id=team_id,
    )


class TestFormatPerformance:
    async def test_returns_formats(self):
        await _seed_publications()
        from bot.services.content_analytics import get_format_performance
        result = await get_format_performance(TEAM)
        assert len(result) >= 2
        kinds = {r["kind"] for r in result}
        assert "text" in kinds
        assert "carousel" in kinds

    async def test_best_format(self):
        await _seed_publications()
        from bot.services.content_analytics import get_format_performance
        result = await get_format_performance(TEAM)
        text_perf = next(r for r in result if r["kind"] == "text")
        assert text_perf["avg_score"] > 3.0
        assert text_perf["count"] == 2


class TestPillarPerformance:
    async def test_returns_pillars(self):
        await _seed_publications()
        from bot.services.content_analytics import get_pillar_performance
        result = await get_pillar_performance(TEAM)
        assert len(result) >= 2
        pillars = {r["pillar"] for r in result}
        assert "Образование" in pillars

    async def test_pillar_scores(self):
        await _seed_publications()
        from bot.services.content_analytics import get_pillar_performance
        result = await get_pillar_performance(TEAM)
        edu = next(r for r in result if r["pillar"] == "Образование")
        assert edu["avg_score"] >= 4.0


class TestTopPublications:
    async def test_returns_top(self):
        await _seed_publications()
        from bot.services.content_analytics import get_top_publications
        result = await get_top_publications(TEAM, limit=3)
        assert len(result) >= 2
        # First should be highest score
        assert result[0]["avg_score"] >= result[-1]["avg_score"]


class TestScoreDistribution:
    async def test_distribution(self):
        await _seed_publications()
        from bot.services.content_analytics import get_score_distribution
        result = await get_score_distribution(TEAM)
        assert isinstance(result, dict)
        total = sum(result.values())
        assert total == 3  # 3 rated publications


class TestBuildPerformanceText:
    async def test_builds_text(self):
        await _seed_publications()
        from bot.services.content_analytics import build_own_performance_text
        text = await build_own_performance_text(TEAM)
        assert "Лучший формат" in text
        assert "text" in text or "carousel" in text

    async def test_empty_when_no_data(self):
        from bot.services.content_analytics import build_own_performance_text
        text = await build_own_performance_text("nonexistent-team")
        assert text == ""
