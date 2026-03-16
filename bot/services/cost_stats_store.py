"""Query helpers for API cost analytics."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select

from db.models import ApiCostLog, UserProfile
from db.session import AsyncSessionLocal


async def get_cost_stats(
    since_date: str,
    until_date: str,
) -> dict[str, Any]:
    """Return cost stats grouped by user and by context (agent)."""
    async with AsyncSessionLocal() as session:
        # Per-user totals
        user_q = (
            select(
                ApiCostLog.telegram_id,
                func.sum(ApiCostLog.input_tokens).label("input_tokens"),
                func.sum(ApiCostLog.output_tokens).label("output_tokens"),
                func.sum(ApiCostLog.cost_usd).label("cost_usd"),
                func.count(ApiCostLog.id).label("calls"),
            )
            .filter(
                ApiCostLog.date >= since_date,
                ApiCostLog.date <= until_date,
                ApiCostLog.telegram_id.isnot(None),
            )
            .group_by(ApiCostLog.telegram_id)
            .order_by(func.sum(ApiCostLog.cost_usd).desc())
        )
        user_rows = (await session.execute(user_q)).all()

        # Per-context (agent) totals
        ctx_q = (
            select(
                ApiCostLog.context,
                ApiCostLog.model,
                func.sum(ApiCostLog.cost_usd).label("cost_usd"),
                func.count(ApiCostLog.id).label("calls"),
            )
            .filter(
                ApiCostLog.date >= since_date,
                ApiCostLog.date <= until_date,
            )
            .group_by(ApiCostLog.context, ApiCostLog.model)
            .order_by(func.sum(ApiCostLog.cost_usd).desc())
        )
        ctx_rows = (await session.execute(ctx_q)).all()

        # Total
        total_q = select(
            func.sum(ApiCostLog.cost_usd),
            func.sum(ApiCostLog.input_tokens),
            func.sum(ApiCostLog.output_tokens),
            func.count(ApiCostLog.id),
        ).filter(
            ApiCostLog.date >= since_date,
            ApiCostLog.date <= until_date,
        )
        total_row = (await session.execute(total_q)).one()

        # Fetch user tiers for display
        tids = [r.telegram_id for r in user_rows if r.telegram_id]
        tier_map: dict[int, str] = {}
        if tids:
            profiles = (
                await session.execute(
                    select(UserProfile).filter(UserProfile.telegram_id.in_(tids))
                )
            ).scalars().all()
            tier_map = {p.telegram_id: p.tier for p in profiles}

    return {
        "since": since_date,
        "until": until_date,
        "total_cost_usd": float(total_row[0] or 0),
        "total_input_tokens": int(total_row[1] or 0),
        "total_output_tokens": int(total_row[2] or 0),
        "total_calls": int(total_row[3] or 0),
        "by_user": [
            {
                "telegram_id": r.telegram_id,
                "tier": tier_map.get(r.telegram_id, "?"),
                "cost_usd": float(r.cost_usd or 0),
                "input_tokens": int(r.input_tokens or 0),
                "output_tokens": int(r.output_tokens or 0),
                "calls": int(r.calls),
            }
            for r in user_rows
        ],
        "by_agent": [
            {
                "context": r.context or "unknown",
                "model": r.model,
                "cost_usd": float(r.cost_usd or 0),
                "calls": int(r.calls),
            }
            for r in ctx_rows
        ],
    }


def date_range_today() -> tuple[str, str]:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return today, today


def date_range_last7() -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    since = (now - timedelta(days=6)).strftime("%Y-%m-%d")
    until = now.strftime("%Y-%m-%d")
    return since, until
