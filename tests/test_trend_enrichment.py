"""Tests for trend enrichment: velocity, convergence, lifecycle, and intelligence."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

import db.session as _db_session
from db.models import CollectorHealth, TrendSignal


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _insert_signal(
    keyword: str,
    source_key: str = "google_trends_en",
    score_raw: float = 10.0,
    collected_at: datetime | None = None,
    lifecycle_stage: str = "",
    velocity: float = 0.0,
    convergence_score: float = 0.0,
    sentiment: str = "",
) -> TrendSignal:
    now = collected_at or datetime.now(timezone.utc)
    async with _db_session.AsyncSessionLocal() as session:
        sig = TrendSignal(
            source_key=source_key,
            keyword=keyword,
            score_raw=score_raw,
            collected_at=now,
            lifecycle_stage=lifecycle_stage,
            velocity=velocity,
            convergence_score=convergence_score,
            sentiment=sentiment,
            items_json={"summary": "test summary"},
        )
        session.add(sig)
        await session.commit()
        await session.refresh(sig)
        return sig


async def _insert_health(source_key: str, last_success: datetime | None = None) -> None:
    async with _db_session.AsyncSessionLocal() as session:
        h = CollectorHealth(
            source_key=source_key,
            last_success=last_success or datetime.now(timezone.utc),
            consecutive_failures=0,
        )
        session.add(h)
        await session.commit()


# ---------------------------------------------------------------------------
# Velocity
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_velocity_with_history(setup_test_db):
    """Velocity should reflect change between current and 7-day-old score."""
    from analytics.signal_enricher import calculate_velocity

    now = datetime.now(timezone.utc)
    seven_days_ago = now - timedelta(days=7)

    # Historical signal: score 10
    await _insert_signal("lavender", score_raw=10.0, collected_at=seven_days_ago)
    # Current signal: score 20
    await _insert_signal("lavender", score_raw=20.0, collected_at=now)

    vel = await calculate_velocity("lavender")
    # (20 - 10) / 10 = 1.0
    assert abs(vel - 1.0) < 0.01


@pytest.mark.asyncio
async def test_velocity_no_history(setup_test_db):
    """Velocity should be 0 when no historical data exists."""
    from analytics.signal_enricher import calculate_velocity

    await _insert_signal("peppermint", score_raw=15.0)
    vel = await calculate_velocity("peppermint")
    assert vel == 0.0


@pytest.mark.asyncio
async def test_velocity_unknown_keyword(setup_test_db):
    """Velocity should be 0 for unknown keyword."""
    from analytics.signal_enricher import calculate_velocity

    vel = await calculate_velocity("nonexistent")
    assert vel == 0.0


# ---------------------------------------------------------------------------
# Convergence
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_convergence_multiple_sources(setup_test_db):
    """Convergence should reflect fraction of active sources mentioning keyword."""
    from analytics.signal_enricher import calculate_convergence

    now = datetime.now(timezone.utc)
    # 3 active sources
    for src in ["google_trends_en", "reddit", "youtube"]:
        await _insert_health(src)

    # Keyword appears in 2 of 3 sources
    await _insert_signal("sound bath", source_key="google_trends_en", collected_at=now)
    await _insert_signal("sound bath", source_key="reddit", collected_at=now)

    conv = await calculate_convergence("sound bath")
    # 2/3 ≈ 0.667
    assert abs(conv - 2 / 3) < 0.01


@pytest.mark.asyncio
async def test_convergence_no_active_sources(setup_test_db):
    """Convergence should be 0 when no active sources exist."""
    from analytics.signal_enricher import calculate_convergence

    await _insert_signal("rose oil")
    conv = await calculate_convergence("rose oil")
    assert conv == 0.0


@pytest.mark.asyncio
async def test_convergence_single_source(setup_test_db):
    """Convergence with 1 source out of 1 active = 1.0."""
    from analytics.signal_enricher import calculate_convergence

    await _insert_health("google_trends_en")
    await _insert_signal("frankincense", source_key="google_trends_en")
    conv = await calculate_convergence("frankincense")
    assert abs(conv - 1.0) < 0.01


# ---------------------------------------------------------------------------
# Lifecycle heuristic
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_lifecycle_emerging(setup_test_db):
    """High velocity + young keyword = emerging."""
    from analytics.signal_enricher import _classify_lifecycle_heuristic

    result = _classify_lifecycle_heuristic("new trend", velocity=0.8, history_days=30, age_days=3)
    assert result == "emerging"


@pytest.mark.asyncio
async def test_lifecycle_growing(setup_test_db):
    """Moderate positive velocity = growing."""
    from analytics.signal_enricher import _classify_lifecycle_heuristic

    result = _classify_lifecycle_heuristic("growing trend", velocity=0.3, history_days=30, age_days=15)
    assert result == "growing"


@pytest.mark.asyncio
async def test_lifecycle_declining(setup_test_db):
    """Negative velocity = declining."""
    from analytics.signal_enricher import _classify_lifecycle_heuristic

    result = _classify_lifecycle_heuristic("old trend", velocity=-0.5, history_days=30, age_days=20)
    assert result == "declining"


@pytest.mark.asyncio
async def test_lifecycle_evergreen(setup_test_db):
    """Low velocity + old keyword = evergreen."""
    from analytics.signal_enricher import _classify_lifecycle_heuristic

    result = _classify_lifecycle_heuristic("stable trend", velocity=0.05, history_days=30, age_days=60)
    assert result == "evergreen"


@pytest.mark.asyncio
async def test_lifecycle_peaking(setup_test_db):
    """Default case = peaking."""
    from analytics.signal_enricher import _classify_lifecycle_heuristic

    result = _classify_lifecycle_heuristic("hot trend", velocity=0.15, history_days=30, age_days=10)
    assert result == "peaking"


# ---------------------------------------------------------------------------
# Opportunity scoring
# ---------------------------------------------------------------------------

def test_opportunity_scoring():
    """Opportunity score = relevance * velocity_factor * convergence."""
    from analytics.trend_intelligence import score_opportunity

    # High relevance, high velocity, high convergence
    score = score_opportunity(relevance=1.0, velocity=1.0, convergence=1.0)
    assert score == 2.0  # 1.0 * (1.0 + 1.0) * 1.0

    # Zero velocity
    score = score_opportunity(relevance=1.0, velocity=0.0, convergence=1.0)
    assert score == 1.0  # 1.0 * 1.0 * 1.0

    # Negative velocity (declining)
    score = score_opportunity(relevance=1.0, velocity=-0.5, convergence=1.0)
    assert abs(score - 0.5) < 0.01  # 1.0 * 0.5 * 1.0

    # Zero convergence uses floor of 0.1
    score = score_opportunity(relevance=1.0, velocity=0.0, convergence=0.0)
    assert abs(score - 0.1) < 0.01


# ---------------------------------------------------------------------------
# Full enrichment pipeline
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_enrich_signals_pipeline(setup_test_db):
    """enrich_signals should update velocity, convergence, lifecycle on recent signals."""
    from analytics.signal_enricher import enrich_signals

    now = datetime.now(timezone.utc)
    seven_days_ago = now - timedelta(days=7)

    await _insert_health("google_trends_en")
    # Historical signal (already enriched, won't be re-processed)
    await _insert_signal(
        "lavender oil", score_raw=10.0, collected_at=seven_days_ago,
        lifecycle_stage="growing",
    )
    # Recent un-enriched signal
    await _insert_signal("lavender oil", score_raw=20.0, collected_at=now)

    count = await enrich_signals()
    assert count == 1

    # Verify the signal was enriched
    async with _db_session.AsyncSessionLocal() as session:
        from sqlalchemy import select
        rows = (
            await session.execute(
                select(TrendSignal)
                .where(TrendSignal.keyword == "lavender oil", TrendSignal.lifecycle_stage != "")
                .order_by(TrendSignal.collected_at.desc())
            )
        ).scalars().all()
        assert len(rows) >= 1
        latest = rows[0]
        assert latest.lifecycle_stage != ""
        assert latest.velocity != 0.0  # Should have calculated velocity


# ---------------------------------------------------------------------------
# Trend intelligence report
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_trend_report(setup_test_db):
    """generate_trend_report should return structured report from enriched signals."""
    from analytics.trend_intelligence import generate_trend_report

    now = datetime.now(timezone.utc)

    # Insert enriched signals
    await _insert_signal(
        "aromatherapy trends", score_raw=50.0, collected_at=now,
        source_key="google_trends_en",
        lifecycle_stage="emerging", velocity=0.8, convergence_score=0.5,
        sentiment="positive",
    )
    await _insert_signal(
        "sound healing", score_raw=30.0, collected_at=now,
        source_key="youtube",
        lifecycle_stage="growing", velocity=0.3, convergence_score=0.3,
        sentiment="neutral",
    )
    await _insert_signal(
        "crystal healing", score_raw=5.0, collected_at=now,
        source_key="reddit",
        lifecycle_stage="declining", velocity=-0.4, convergence_score=0.1,
        sentiment="negative",
    )

    report = await generate_trend_report()

    assert "top_opportunities" in report
    assert "emerging_signals" in report
    assert "declining_topics" in report
    assert "generated_at" in report
    assert report["total_signals_analyzed"] == 3

    # Emerging signals should include "aromatherapy trends"
    emerging_kws = [e["keyword"] for e in report["emerging_signals"]]
    assert "aromatherapy trends" in emerging_kws

    # Declining should include "crystal healing"
    declining_kws = [d["keyword"] for d in report["declining_topics"]]
    assert "crystal healing" in declining_kws

    # Top opportunities should have the right structure
    top = report["top_opportunities"][0]
    assert "keyword" in top
    assert "score" in top
    assert "velocity" in top
    assert "convergence" in top
    assert "lifecycle" in top
    assert "suggested_formats" in top
    assert "content_angle" in top


# ---------------------------------------------------------------------------
# Brand relevance
# ---------------------------------------------------------------------------

def test_brand_relevance():
    """Brand relevance should score brand keywords higher."""
    from analytics.trend_intelligence import _brand_relevance

    assert _brand_relevance("aromatherapy") == 1.0
    assert _brand_relevance("singing bowls meditation") == 1.0
    assert _brand_relevance("wellness tips") >= 0.6
    assert _brand_relevance("cryptocurrency news") == 0.2
