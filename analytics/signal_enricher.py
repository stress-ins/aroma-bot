"""Post-collection AI enrichment pass for raw trend signals.

Adds velocity, convergence, lifecycle stage, and sentiment to TrendSignal rows.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from db.models import CollectorHealth, TrendSignal
from db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)


async def enrich_signals(source_key: str | None = None, max_age_hours: int = 24) -> int:
    """Enrich recent raw signals with velocity, convergence, lifecycle, sentiment.

    Returns number of signals enriched.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    async with AsyncSessionLocal() as session:
        q = select(TrendSignal).where(
            TrendSignal.collected_at >= cutoff,
            # Only enrich signals that haven't been enriched yet
            TrendSignal.lifecycle_stage == "",
        )
        if source_key is not None:
            q = q.where(TrendSignal.source_key == source_key)
        rows = (await session.execute(q)).scalars().all()

    enriched = 0
    for sig in rows:
        try:
            velocity = await calculate_velocity(sig.keyword)
            convergence = await calculate_convergence(sig.keyword)
            lifecycle = await classify_lifecycle(sig.keyword, velocity)
            sentiment = await _maybe_analyze_sentiment(sig)

            async with AsyncSessionLocal() as session:
                row = (
                    await session.execute(
                        select(TrendSignal).where(TrendSignal.id == sig.id)
                    )
                ).scalar_one_or_none()
                if row is not None:
                    row.velocity = velocity
                    row.convergence_score = convergence
                    row.lifecycle_stage = lifecycle
                    row.sentiment = sentiment
                    await session.commit()
                    enriched += 1
        except Exception:
            logger.exception("Failed to enrich signal %s/%s", sig.source_key, sig.keyword)

    logger.info("Enriched %d signals", enriched)
    return enriched


async def calculate_velocity(keyword: str) -> float:
    """Compare current score vs 7 days ago. Returns percentage change."""
    now = datetime.now(timezone.utc)
    seven_days_ago = now - timedelta(days=7)
    window_start = seven_days_ago - timedelta(hours=12)
    window_end = seven_days_ago + timedelta(hours=12)

    async with AsyncSessionLocal() as session:
        # Current score: latest signal for this keyword
        current_q = (
            select(TrendSignal.score_raw)
            .where(TrendSignal.keyword == keyword)
            .order_by(TrendSignal.collected_at.desc())
            .limit(1)
        )
        score_now = (await session.execute(current_q)).scalar_one_or_none()

        # Score ~7 days ago
        hist_q = (
            select(func.avg(TrendSignal.score_raw))
            .where(
                TrendSignal.keyword == keyword,
                TrendSignal.collected_at >= window_start,
                TrendSignal.collected_at <= window_end,
            )
        )
        score_7d = (await session.execute(hist_q)).scalar_one_or_none()

    if score_now is None:
        return 0.0
    if score_7d is None or score_7d == 0:
        # Fallback: use the oldest available signal as baseline
        async with AsyncSessionLocal() as session:
            oldest_q = (
                select(TrendSignal.score_raw)
                .where(
                    TrendSignal.keyword == keyword,
                    TrendSignal.collected_at < now - timedelta(hours=1),
                )
                .order_by(TrendSignal.collected_at.asc())
                .limit(1)
            )
            score_7d = (await session.execute(oldest_q)).scalar_one_or_none()
        if score_7d is None or score_7d == 0:
            return 0.0

    return (score_now - score_7d) / max(score_7d, 1.0)


async def calculate_convergence(keyword: str, lookback_hours: int = 24) -> float:
    """How many different sources mention this keyword? Returns 0.0-1.0."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

    async with AsyncSessionLocal() as session:
        # Count distinct sources for this keyword
        src_q = (
            select(func.count(func.distinct(TrendSignal.source_key)))
            .where(
                TrendSignal.keyword == keyword,
                TrendSignal.collected_at >= cutoff,
            )
        )
        keyword_sources = (await session.execute(src_q)).scalar_one_or_none() or 0

        # Total active sources: CollectorHealth with recent success
        health_cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
        total_q = select(func.count()).where(
            CollectorHealth.last_success.is_not(None),
            CollectorHealth.last_success >= health_cutoff,
        )
        total_active = (await session.execute(total_q)).scalar_one_or_none() or 0

    if total_active == 0:
        return 0.0

    return min(keyword_sources / total_active, 1.0)


async def classify_lifecycle(
    keyword: str, velocity: float, history_days: int = 30
) -> str:
    """Classify trend as emerging|growing|peaking|declining|evergreen.

    Uses heuristic based on velocity and age of first signal.
    Falls back to Claude Haiku if available.
    """
    # Try Claude-based classification first
    lifecycle = await _classify_lifecycle_with_llm(keyword, velocity, history_days)
    if lifecycle:
        return lifecycle

    # Heuristic fallback
    return _classify_lifecycle_heuristic(keyword, velocity, history_days, age_days=await _keyword_age_days(keyword))


async def _keyword_age_days(keyword: str) -> float:
    """Return the age in days of the first signal for this keyword."""
    async with AsyncSessionLocal() as session:
        q = (
            select(TrendSignal.collected_at)
            .where(TrendSignal.keyword == keyword)
            .order_by(TrendSignal.collected_at.asc())
            .limit(1)
        )
        first_seen = (await session.execute(q)).scalar_one_or_none()

    if first_seen is None:
        return 0.0
    if first_seen.tzinfo is None:
        first_seen = first_seen.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - first_seen
    return delta.total_seconds() / 86400


def _classify_lifecycle_heuristic(
    keyword: str, velocity: float, history_days: int, age_days: float
) -> str:
    """Pure heuristic lifecycle classification — no LLM needed."""
    if velocity > 0.5 and age_days < 7:
        return "emerging"
    if velocity > 0.2:
        return "growing"
    if velocity < -0.2:
        return "declining"
    if abs(velocity) < 0.1 and age_days > 30:
        return "evergreen"
    return "peaking"


async def _classify_lifecycle_with_llm(
    keyword: str, velocity: float, history_days: int
) -> str | None:
    """Try to classify with Claude Haiku via call_claude(). Returns None if unavailable."""
    try:
        # Get score history
        cutoff = datetime.now(timezone.utc) - timedelta(days=history_days)
        async with AsyncSessionLocal() as session:
            q = (
                select(TrendSignal.collected_at, TrendSignal.score_raw)
                .where(
                    TrendSignal.keyword == keyword,
                    TrendSignal.collected_at >= cutoff,
                )
                .order_by(TrendSignal.collected_at.asc())
            )
            rows = (await session.execute(q)).all()

        if len(rows) < 3:
            return None  # Not enough data for LLM

        history_text = "\n".join(
            f"{r.collected_at.strftime('%Y-%m-%d')}: {r.score_raw:.1f}" for r in rows
        )

        import asyncio
        from bot.services.claude_client import HAIKU, call_claude

        prompt = (
            f'Classify the trend lifecycle stage for keyword "{keyword}".\n'
            f"Velocity (7d change): {velocity:.2f}\n"
            f"Score history (last {history_days} days):\n{history_text}\n\n"
            "Reply with exactly one word: emerging, growing, peaking, declining, or evergreen."
        )
        result = await asyncio.get_running_loop().run_in_executor(
            None, lambda: call_claude(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=50, model=HAIKU, context="signal_enricher",
            ),
        )
        result = result.strip().lower()
        valid = {"emerging", "growing", "peaking", "declining", "evergreen"}
        return result if result in valid else None
    except Exception:
        logger.debug("LLM lifecycle classification unavailable, using heuristic")
        return None


async def analyze_sentiment(keyword: str, sample_texts: list[str]) -> str:
    """Lightweight sentiment for text-bearing signals. Returns positive|neutral|negative."""
    if not sample_texts:
        return "neutral"

    try:
        import asyncio
        from bot.services.claude_client import HAIKU, call_claude

        combined = "\n---\n".join(sample_texts[:5])  # Limit to 5 samples
        prompt = (
            f'What is the overall sentiment about "{keyword}" in these texts?\n\n'
            f"{combined}\n\n"
            "Reply with exactly one word: positive, neutral, or negative."
        )
        result = await asyncio.get_running_loop().run_in_executor(
            None, lambda: call_claude(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=20, model=HAIKU, context="signal_enricher_sentiment",
            ),
        )
        result = result.strip().lower()
        valid = {"positive", "neutral", "negative"}
        return result if result in valid else "neutral"
    except Exception:
        logger.debug("LLM sentiment analysis unavailable")
        return "neutral"


async def _maybe_analyze_sentiment(sig: TrendSignal) -> str:
    """Analyze sentiment if the signal has text content."""
    items = sig.items_json or {}
    texts = []
    summary = items.get("summary", "")
    if summary:
        texts.append(summary)
    extra = items.get("extra", "")
    if extra:
        texts.append(extra)

    if not texts:
        return "neutral"

    return await analyze_sentiment(sig.keyword, texts)
