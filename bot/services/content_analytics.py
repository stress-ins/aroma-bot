"""Content analytics for past publications — aggregations for stats and plan generation."""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import func, case, select

from db.models import PastPublicationModel
from db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)


async def get_format_performance(team_id: str | None = None) -> list[dict[str, Any]]:
    """Average score and count per content format (kind)."""
    async with AsyncSessionLocal() as session:
        cols = [
            PastPublicationModel.kind,
            func.count().label("count"),
            func.avg(PastPublicationModel.score_engagement).label("avg_engagement"),
            func.avg(PastPublicationModel.score_brand_fit).label("avg_brand"),
            func.avg(PastPublicationModel.score_craft).label("avg_craft"),
            func.avg(PastPublicationModel.score_goal_hit).label("avg_goal"),
        ]
        query = select(*cols).group_by(PastPublicationModel.kind)
        if team_id:
            query = query.filter(PastPublicationModel.team_id == team_id)
        # Only include rated publications
        query = query.filter(PastPublicationModel.score_engagement.isnot(None))
        result = await session.execute(query)
        rows = result.all()
        return [
            {
                "kind": r.kind,
                "count": r.count,
                "avg_score": round(
                    sum(v for v in [r.avg_engagement, r.avg_brand, r.avg_craft, r.avg_goal] if v is not None)
                    / max(sum(1 for v in [r.avg_engagement, r.avg_brand, r.avg_craft, r.avg_goal] if v is not None), 1),
                    1,
                ),
            }
            for r in rows
        ]


async def get_pillar_performance(team_id: str | None = None) -> list[dict[str, Any]]:
    """Average score per content pillar."""
    async with AsyncSessionLocal() as session:
        cols = [
            PastPublicationModel.content_pillar,
            func.count().label("count"),
            func.avg(PastPublicationModel.score_engagement).label("avg_eng"),
            func.avg(PastPublicationModel.score_brand_fit).label("avg_brand"),
            func.avg(PastPublicationModel.score_craft).label("avg_craft"),
            func.avg(PastPublicationModel.score_goal_hit).label("avg_goal"),
        ]
        query = (
            select(*cols)
            .filter(PastPublicationModel.content_pillar != "")
            .group_by(PastPublicationModel.content_pillar)
        )
        if team_id:
            query = query.filter(PastPublicationModel.team_id == team_id)
        query = query.filter(PastPublicationModel.score_engagement.isnot(None))
        result = await session.execute(query)
        rows = result.all()
        return [
            {
                "pillar": r.content_pillar,
                "count": r.count,
                "avg_score": round(
                    sum(v for v in [r.avg_eng, r.avg_brand, r.avg_craft, r.avg_goal] if v is not None)
                    / max(sum(1 for v in [r.avg_eng, r.avg_brand, r.avg_craft, r.avg_goal] if v is not None), 1),
                    1,
                ),
            }
            for r in rows
        ]


async def get_top_publications(team_id: str | None = None, limit: int = 5) -> list[dict[str, Any]]:
    """Top publications by average score."""
    M = PastPublicationModel
    avg_expr = (
        func.coalesce(M.score_engagement, 0)
        + func.coalesce(M.score_brand_fit, 0)
        + func.coalesce(M.score_craft, 0)
        + func.coalesce(M.score_goal_hit, 0)
    ) / (
        case((M.score_engagement.isnot(None), 1), else_=0)
        + case((M.score_brand_fit.isnot(None), 1), else_=0)
        + case((M.score_craft.isnot(None), 1), else_=0)
        + case((M.score_goal_hit.isnot(None), 1), else_=0)
    )
    query = (
        select(M, avg_expr.label("avg_score"))
        .filter(M.score_engagement.isnot(None))
        .order_by(avg_expr.desc())
        .limit(limit)
    )
    if team_id:
        query = query.filter(M.team_id == team_id)
    async with AsyncSessionLocal() as session:
        result = await session.execute(query)
        rows = result.all()
        return [
            {
                "pub_id": r[0].pub_id,
                "topic": r[0].topic,
                "kind": r[0].kind,
                "platform": r[0].platform,
                "avg_score": round(float(r[1]), 1) if r[1] else 0,
            }
            for r in rows
        ]


async def get_score_distribution(team_id: str | None = None) -> dict[int, int]:
    """Distribution of average scores (1-5) across rated publications."""
    M = PastPublicationModel
    async with AsyncSessionLocal() as session:
        query = select(
            M.score_engagement, M.score_brand_fit, M.score_craft, M.score_goal_hit
        ).filter(M.score_engagement.isnot(None))
        if team_id:
            query = query.filter(M.team_id == team_id)
        result = await session.execute(query)
        rows = result.all()

    dist: dict[int, int] = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for r in rows:
        scores = [s for s in r if s is not None]
        if scores:
            avg = round(sum(scores) / len(scores))
            avg = max(1, min(5, avg))
            dist[avg] = dist.get(avg, 0) + 1
    return dist


async def build_own_performance_text(team_id: str) -> str:
    """Build past publication stats for plan prompt enrichment."""
    try:
        formats = await get_format_performance(team_id)
        pillars = await get_pillar_performance(team_id)
        top = await get_top_publications(team_id, limit=3)
    except Exception:
        logger.debug("content_analytics: failed to build performance text", exc_info=True)
        return ""

    if not formats and not pillars:
        return ""

    parts = ["\nАналитика прошлых публикаций автора:"]

    if formats:
        best_format = max(formats, key=lambda f: f["avg_score"])
        parts.append(f"- Лучший формат: {best_format['kind']} (ø {best_format['avg_score']}★, {best_format['count']} публ.)")
        for f in formats:
            if f["kind"] != best_format["kind"]:
                parts.append(f"  · {f['kind']}: ø {f['avg_score']}★ ({f['count']} публ.)")

    if pillars:
        best_pillar = max(pillars, key=lambda p: p["avg_score"])
        parts.append(f"- Лучший столп контента: {best_pillar['pillar']} (ø {best_pillar['avg_score']}★)")

    if top:
        parts.append("- Топ публикации:")
        for t in top:
            parts.append(f"  · «{t['topic']}» ({t['kind']}, {t['platform']}) — {t['avg_score']}★")

    parts.append("Учитывай эти данные при составлении плана: делай акцент на успешных форматах и темах.")
    return "\n".join(parts)
