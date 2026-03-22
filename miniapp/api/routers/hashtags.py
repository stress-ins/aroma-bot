"""Hashtag Recommender API router."""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from bot.services.drafts_store import get_draft, update_draft

from ..auth import _require_auth, require_tier

logger = logging.getLogger(__name__)
router = APIRouter()
_executor = ThreadPoolExecutor(max_workers=2)


class HashtagRecommendRequest(BaseModel):
    text: str = Field(..., min_length=10, max_length=3000)
    platform: str = Field(default="instagram")
    count: int = Field(default=12, ge=5, le=20)


class HashtagApplyRequest(BaseModel):
    draft_id: str = Field(..., min_length=1)
    hashtags: list[str] = Field(..., min_length=1, max_length=20)


@router.post("/api/hashtags/recommend", dependencies=[Depends(require_tier("expert"))])
async def recommend_hashtags(body: HashtagRecommendRequest):
    """Recommend hashtags for post text."""
    from bot.agents.hashtag_recommender import recommend_hashtags_sync

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        _executor, recommend_hashtags_sync, body.text, body.platform, body.count,
    )
    return result


@router.get("/api/hashtags/library", dependencies=[Depends(_require_auth)])
async def hashtag_library(
    category: str = Query("", description="Filter by category"),
    tier: str = Query("", description="Filter by tier: high, medium, niche"),
):
    """Browse the hashtag library."""
    from bot.agents.hashtag_recommender import get_library

    result = get_library(
        category=category or None,
        tier=tier or None,
    )
    return {"items": result, "total": len(result)}


@router.post("/api/hashtags/apply", dependencies=[Depends(require_tier("expert"))])
async def apply_hashtags(body: HashtagApplyRequest):
    """Apply hashtags to a draft."""
    draft = await get_draft(body.draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="draft_not_found")

    payload = draft.payload or {}
    # Store hashtags as formatted string
    tags_str = " ".join(f"#{t.lstrip('#')}" for t in body.hashtags)
    payload["hashtags"] = tags_str
    payload["hashtags_list"] = [t.lstrip("#") for t in body.hashtags]
    await update_draft(body.draft_id, payload=payload)
    return {"ok": True, "hashtags": tags_str}


@router.get("/api/hashtags/quota", dependencies=[Depends(_require_auth)])
async def hashtag_quota():
    """Check Instagram hashtag search API quota."""
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import func, select

    from db.models import HashtagQuotaModel
    from db.session import AsyncSessionLocal

    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(func.count(func.distinct(HashtagQuotaModel.hashtag)))
            .where(HashtagQuotaModel.searched_at >= cutoff)
        )
        used = result.scalar() or 0

    return {
        "used": used,
        "limit": 30,
        "remaining": max(0, 30 - used),
        "period": "7 days",
    }
