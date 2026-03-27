"""Trend intelligence — enriched analysis replacing basic AI recommendations.

Generates structured trend reports with opportunity scoring,
emerging signals, and declining topics.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from db.models import TrendSignal
from db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)

# Brand relevance keywords — topics core to our wellness niche
_BRAND_KEYWORDS = {
    "aromatherapy", "essential oils", "sound healing", "singing bowls",
    "gong meditation", "olfactotherapy", "wellness", "sound bath",
    "ароматерапия", "эфирные масла", "звуковые ванны", "поющие чаши",
    "гонг медитация", "ольфактотерапия", "велнес",
}


def _brand_relevance(keyword: str) -> float:
    """Score 0.0-1.0 how relevant a keyword is to our brand."""
    kw_lower = keyword.lower()
    # Direct match
    for bk in _BRAND_KEYWORDS:
        if bk in kw_lower or kw_lower in bk:
            return 1.0
    # Partial overlap (any word match)
    kw_words = set(kw_lower.split())
    for bk in _BRAND_KEYWORDS:
        if kw_words & set(bk.split()):
            return 0.6
    return 0.2  # Generic wellness-adjacent


def score_opportunity(relevance: float, velocity: float, convergence: float) -> float:
    """Opportunity = relevance * velocity_factor * convergence.

    velocity_factor is clamped to [0, 2] to avoid extreme swings.
    """
    velocity_factor = max(0.0, min(velocity + 1.0, 2.0))
    return relevance * velocity_factor * max(convergence, 0.1)


_SUGGESTED_FORMATS = {
    "emerging": ["short reel", "carousel explainer", "story poll"],
    "growing": ["in-depth post", "carousel", "live session"],
    "peaking": ["expert opinion", "trend roundup", "collab post"],
    "declining": ["retrospective", "myth-busting"],
    "evergreen": ["educational carousel", "how-to guide", "FAQ post"],
}


async def generate_trend_report() -> dict:
    """Generate enriched trend intelligence report.

    Returns structured dict with top opportunities, emerging signals,
    and declining topics.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=48)

    async with AsyncSessionLocal() as session:
        q = select(TrendSignal).where(
            TrendSignal.collected_at >= cutoff,
            TrendSignal.lifecycle_stage != "",
        )
        signals = (await session.execute(q)).scalars().all()

    # De-duplicate by keyword: keep the latest signal per keyword
    by_keyword: dict[str, TrendSignal] = {}
    for sig in signals:
        existing = by_keyword.get(sig.keyword)
        if existing is None or sig.collected_at > existing.collected_at:
            by_keyword[sig.keyword] = sig

    # Collect sources per keyword
    keyword_sources: dict[str, set[str]] = {}
    for sig in signals:
        keyword_sources.setdefault(sig.keyword, set()).add(sig.source_key)

    opportunities = []
    for kw, sig in by_keyword.items():
        relevance = _brand_relevance(kw)
        opp_score = score_opportunity(relevance, sig.velocity, sig.convergence_score)
        lifecycle = sig.lifecycle_stage or "peaking"
        opportunities.append({
            "keyword": kw,
            "score": round(opp_score, 3),
            "velocity": round(sig.velocity, 3),
            "convergence": round(sig.convergence_score, 3),
            "lifecycle": lifecycle,
            "sentiment": sig.sentiment or "neutral",
            "sources": sorted(keyword_sources.get(kw, set())),
            "suggested_formats": _SUGGESTED_FORMATS.get(lifecycle, []),
            "content_angle": _content_angle(kw, lifecycle, sig.velocity),
        })

    # Sort by opportunity score descending
    opportunities.sort(key=lambda x: x["score"], reverse=True)

    top = opportunities[:10]
    emerging = [o for o in opportunities if o["lifecycle"] == "emerging"][:5]
    declining = [o for o in opportunities if o["lifecycle"] == "declining"][:5]

    return {
        "top_opportunities": top,
        "emerging_signals": emerging,
        "declining_topics": declining,
        "total_signals_analyzed": len(by_keyword),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _content_angle(keyword: str, lifecycle: str, velocity: float) -> str:
    """Generate a brief content angle suggestion in Russian."""
    if lifecycle == "emerging":
        return f'Ранний тренд: «{keyword}» набирает обороты. Займите позицию эксперта первым.'
    if lifecycle == "growing":
        return f'Растущий интерес к теме «{keyword}». Создайте образовательный контент для захвата поискового трафика.'
    if lifecycle == "peaking":
        return f'«{keyword}» на пике внимания. Поделитесь экспертным мнением, пока интерес высок.'
    if lifecycle == "declining":
        return f'Интерес к «{keyword}» снижается. Используйте ретроспективный или разоблачающий мифы формат.'
    if lifecycle == "evergreen":
        return f'«{keyword}» имеет стабильный спрос. Создайте подробный SEO-оптимизированный контент.'
    return f'Раскройте тему «{keyword}» с точки зрения ароматерапии и велнеса.'
