"""Smart Schedule API router."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query

from ..auth import TeamContext, _require_auth, _resolve_team_context

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api/schedule/recommend", dependencies=[Depends(_require_auth)])
async def recommend_schedule(
    topic: str = Query("", description="Post topic for context-aware timing"),
    platform: str = Query("instagram", description="Target platform"),
    kind: str = Query("instagram", description="Content kind"),
    ctx: TeamContext = Depends(_resolve_team_context),
):
    from bot.agents.schedule_advisor import recommend_schedule as _recommend
    return await _recommend(topic=topic, platform=platform, kind=kind, team_id=ctx.team_id, top_k=3)


@router.get("/api/schedule/heatmap", dependencies=[Depends(_require_auth)])
async def schedule_heatmap(
    platform: str = Query("instagram"),
    period_days: int = Query(30, ge=7, le=90),
    ctx: TeamContext = Depends(_resolve_team_context),
):
    if not ctx.team_id:
        return {"heatmap": {}, "period_days": period_days, "has_data": False}
    try:
        from bot.services.social_trends_store import get_posting_heatmap
        heatmap = await get_posting_heatmap(ctx.team_id, platform, period_days)
        return {"heatmap": heatmap, "period_days": period_days, "has_data": bool(heatmap)}
    except Exception:
        return {"heatmap": {}, "period_days": period_days, "has_data": False}
