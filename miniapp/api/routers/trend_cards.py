"""Trend Cards API router."""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from bot.services.drafts_store import save_draft
from bot.services.miniapp_presenter import serialize_draft

from ..auth import TeamContext, _require_auth, _resolve_team_context, require_tier

logger = logging.getLogger(__name__)
router = APIRouter()


class CreateFromTrendRequest(BaseModel):
    card_id: str = Field(..., min_length=1)
    format_key: str = Field(default="instagram")
    goal_key: str = Field(default="trust")


@router.get("/api/trends/cards", dependencies=[Depends(_require_auth)])
async def list_trend_cards(
    limit: int = Query(10, ge=1, le=50),
    lifecycle: str = Query("", description="Filter: emerging, growing, peaking, declining"),
    min_strength: float = Query(0.0, ge=0, le=1),
    ctx: TeamContext = Depends(_resolve_team_context),
):
    """List trend cards."""
    from datetime import datetime, timezone

    from sqlalchemy import select

    from db.models import TrendCardModel
    from db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        q = select(TrendCardModel).order_by(TrendCardModel.strength.desc()).limit(limit)
        if ctx.team_id:
            q = q.where(
                (TrendCardModel.team_id == ctx.team_id) | (TrendCardModel.team_id.is_(None))
            )
        if lifecycle:
            q = q.where(TrendCardModel.lifecycle == lifecycle)
        if min_strength > 0:
            q = q.where(TrendCardModel.strength >= min_strength)

        result = await session.execute(q)
        cards = []
        now = datetime.now(timezone.utc)
        for row in result.scalars():
            if row.expires_at and row.expires_at < now:
                continue
            cards.append({
                "card_id": row.card_id,
                "keyword": row.keyword,
                "title": row.title,
                "strength": row.strength,
                "lifecycle": row.lifecycle,
                "sentiment": row.sentiment,
                "summary": row.summary,
                "recommendation": row.recommendation,
                "suggested_formats": row.suggested_formats or [],
                "velocity": row.velocity,
                "convergence": row.convergence,
                "created_at": row.created_at.isoformat() if row.created_at else "",
            })

    return {"cards": cards}


@router.get("/api/trends/cards/{card_id}", dependencies=[Depends(_require_auth)])
async def get_trend_card(card_id: str):
    """Get single trend card details."""
    from sqlalchemy import select

    from db.models import TrendCardModel
    from db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(TrendCardModel).where(TrendCardModel.card_id == card_id)
        )
        row = result.scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="card_not_found")
        return {
            "card_id": row.card_id,
            "keyword": row.keyword,
            "title": row.title,
            "strength": row.strength,
            "lifecycle": row.lifecycle,
            "sentiment": row.sentiment,
            "summary": row.summary,
            "recommendation": row.recommendation,
            "suggested_formats": row.suggested_formats or [],
            "source_signals": row.source_signals or [],
            "velocity": row.velocity,
            "convergence": row.convergence,
            "created_at": row.created_at.isoformat() if row.created_at else "",
        }


@router.post("/api/trends/cards/generate", dependencies=[Depends(require_tier("expert"))])
async def generate_trend_cards(
    background_tasks: BackgroundTasks,
    ctx: TeamContext = Depends(_resolve_team_context),
):
    """Trigger AI trend card generation from current intelligence report."""
    from bot.agents.trend_card_generator import generate_and_save_cards

    background_tasks.add_task(generate_and_save_cards, ctx.team_id)
    return {"status": "generating", "message": "Генерация карточек запущена"}


@router.post("/api/trends/create-from-trend", dependencies=[Depends(require_tier("expert"))])
async def create_from_trend(
    body: CreateFromTrendRequest,
    background_tasks: BackgroundTasks,
    ctx: TeamContext = Depends(_resolve_team_context),
):
    """Create a content draft from a trend card."""
    from sqlalchemy import select

    from db.models import TrendCardModel
    from db.session import AsyncSessionLocal
    from miniapp.api.generation import complete_content_generation

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(TrendCardModel).where(TrendCardModel.card_id == body.card_id)
        )
        card = result.scalar_one_or_none()
        if not card:
            raise HTTPException(status_code=404, detail="card_not_found")

    topic = f"{card.title}\n\nТренд: {card.keyword}. {card.summary}"
    stub_payload: dict = {
        "generation_pending": True,
        "generation_stage": "content",
        "generation_message": "Создаю контент по тренду...",
        "goal_key": body.goal_key,
        "format_key": body.format_key,
        "trend_card_id": body.card_id,
        "trend_keyword": card.keyword,
    }
    saved = await save_draft(
        kind=body.format_key,
        topic=card.title,
        source="trend_card",
        payload=stub_payload,
        team_id=ctx.team_id,
        created_by=ctx.telegram_id,
    )
    background_tasks.add_task(
        complete_content_generation,
        saved.draft_id, topic, body.goal_key, body.format_key,
    )
    return await serialize_draft(saved)
