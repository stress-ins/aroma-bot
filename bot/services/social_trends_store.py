"""Social trends store — per-team storage for Instagram/Threads collected posts.

All queries are scoped by team_id for multi-tenant isolation.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select

from db.models import (
    BrandSettingsModel,
    HashtagQuotaModel,
    SocialTrendPostModel,
)
from db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------


async def upsert_social_post(
    team_id: str,
    platform: str,
    post_id: str,
    *,
    source_type: str = "account",
    source_value: str = "",
    author_username: str = "",
    text: str = "",
    permalink: str = "",
    media_type: str = "",
    thumbnail_url: str = "",
    hashtags: list[str] | None = None,
    like_count: int = 0,
    comment_count: int = 0,
    share_count: int = 0,
    reply_count: int = 0,
    view_count: int = 0,
    posted_at: datetime | None = None,
) -> None:
    """Insert or update a social post by platform-native post_id."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(SocialTrendPostModel).where(
                SocialTrendPostModel.post_id == post_id
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            row = SocialTrendPostModel(
                team_id=team_id,
                platform=platform,
                post_id=post_id,
                source_type=source_type,
                source_value=source_value,
                author_username=author_username,
                text=text,
                permalink=permalink,
                media_type=media_type,
                thumbnail_url=thumbnail_url,
                hashtags=hashtags or [],
                like_count=like_count,
                comment_count=comment_count,
                share_count=share_count,
                reply_count=reply_count,
                view_count=view_count,
                posted_at=posted_at,
            )
            session.add(row)
        else:
            # Update engagement metrics (they change over time)
            row.like_count = like_count
            row.comment_count = comment_count
            row.share_count = share_count
            row.reply_count = reply_count
            row.view_count = view_count
            row.collected_at = datetime.now(timezone.utc)
            if text:
                row.text = text
            if hashtags is not None:
                row.hashtags = hashtags
        await session.commit()


async def record_hashtag_search(team_id: str, hashtag: str) -> None:
    """Record a hashtag search for quota tracking."""
    async with AsyncSessionLocal() as session:
        session.add(HashtagQuotaModel(
            team_id=team_id,
            hashtag=hashtag.lower().lstrip("#"),
            searched_at=datetime.now(timezone.utc),
        ))
        await session.commit()


async def cleanup_old_posts(days: int = 90) -> int:
    """Delete posts older than `days`. Returns deleted count."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            delete(SocialTrendPostModel).where(
                SocialTrendPostModel.posted_at < cutoff
            )
        )
        await session.commit()
        return result.rowcount  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Read — all scoped by team_id
# ---------------------------------------------------------------------------


async def list_social_posts(
    team_id: str,
    platform: str,
    since: datetime | None = None,
    limit: int = 50,
) -> list[dict]:
    """List posts for a team+platform, newest first."""
    async with AsyncSessionLocal() as session:
        q = (
            select(SocialTrendPostModel)
            .where(
                SocialTrendPostModel.team_id == team_id,
                SocialTrendPostModel.platform == platform,
            )
            .order_by(SocialTrendPostModel.posted_at.desc())
            .limit(limit)
        )
        if since:
            q = q.where(SocialTrendPostModel.posted_at >= since)
        result = await session.execute(q)
        return [_to_dict(r) for r in result.scalars().all()]


async def get_top_posts(
    team_id: str,
    platform: str,
    period_days: int = 7,
    limit: int = 10,
) -> list[dict]:
    """Top posts by total engagement within the period."""
    since = datetime.now(timezone.utc) - timedelta(days=period_days)
    async with AsyncSessionLocal() as session:
        M = SocialTrendPostModel
        engagement = (M.like_count + M.comment_count + M.share_count + M.reply_count)
        q = (
            select(M)
            .where(M.team_id == team_id, M.platform == platform, M.posted_at >= since)
            .order_by(engagement.desc())
            .limit(limit)
        )
        result = await session.execute(q)
        return [_to_dict(r) for r in result.scalars().all()]


async def get_posting_heatmap(
    team_id: str,
    platform: str,
    period_days: int = 7,
) -> dict[int, dict[int, int]]:
    """Returns {weekday(0-6): {hour(0-23): post_count}}."""
    since = datetime.now(timezone.utc) - timedelta(days=period_days)
    async with AsyncSessionLocal() as session:
        M = SocialTrendPostModel
        q = (
            select(M.posted_at)
            .where(
                M.team_id == team_id,
                M.platform == platform,
                M.posted_at >= since,
                M.posted_at.isnot(None),
            )
        )
        result = await session.execute(q)
        heatmap: dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))
        for (posted_at,) in result.all():
            if posted_at:
                heatmap[posted_at.weekday()][posted_at.hour] += 1
        return {day: dict(hours) for day, hours in heatmap.items()}


async def get_hashtag_stats(
    team_id: str,
    platform: str,
    period_days: int = 7,
    limit: int = 20,
) -> list[dict]:
    """Top hashtags by frequency within the period."""
    since = datetime.now(timezone.utc) - timedelta(days=period_days)
    async with AsyncSessionLocal() as session:
        M = SocialTrendPostModel
        q = (
            select(M.hashtags)
            .where(M.team_id == team_id, M.platform == platform, M.posted_at >= since)
        )
        result = await session.execute(q)
        counter: dict[str, int] = defaultdict(int)
        for (tags,) in result.all():
            if tags:
                for tag in tags:
                    counter[tag.lower()] += 1
        sorted_tags = sorted(counter.items(), key=lambda x: x[1], reverse=True)
        return [{"tag": t, "count": c} for t, c in sorted_tags[:limit]]


async def get_format_breakdown(
    team_id: str,
    platform: str,
    period_days: int = 7,
) -> dict[str, int]:
    """Count posts per media_type."""
    since = datetime.now(timezone.utc) - timedelta(days=period_days)
    async with AsyncSessionLocal() as session:
        M = SocialTrendPostModel
        q = (
            select(M.media_type, func.count(M.id))
            .where(M.team_id == team_id, M.platform == platform, M.posted_at >= since)
            .group_by(M.media_type)
        )
        result = await session.execute(q)
        return {mt or "unknown": cnt for mt, cnt in result.all()}


async def get_content_length_breakdown(
    team_id: str,
    period_days: int = 7,
) -> dict[str, int]:
    """Classify posts by text length: short (<100), medium (100-300), long (>300)."""
    since = datetime.now(timezone.utc) - timedelta(days=period_days)
    async with AsyncSessionLocal() as session:
        M = SocialTrendPostModel
        q = select(M.text).where(M.team_id == team_id, M.posted_at >= since)
        result = await session.execute(q)
        breakdown: dict[str, int] = {"short": 0, "medium": 0, "long": 0}
        for (text,) in result.all():
            length = len(text or "")
            if length < 100:
                breakdown["short"] += 1
            elif length <= 300:
                breakdown["medium"] += 1
            else:
                breakdown["long"] += 1
        return breakdown


async def get_best_posting_times(
    team_id: str,
    platform: str,
    period_days: int = 7,
) -> list[dict]:
    """Returns top posting hours ranked by average engagement."""
    since = datetime.now(timezone.utc) - timedelta(days=period_days)
    async with AsyncSessionLocal() as session:
        M = SocialTrendPostModel
        q = (
            select(M.posted_at, M.like_count, M.comment_count, M.share_count, M.reply_count)
            .where(
                M.team_id == team_id,
                M.platform == platform,
                M.posted_at >= since,
                M.posted_at.isnot(None),
            )
        )
        result = await session.execute(q)
        hour_stats: dict[int, list[int]] = defaultdict(list)
        for posted_at, likes, comments, shares, replies in result.all():
            if posted_at:
                total = (likes or 0) + (comments or 0) + (shares or 0) + (replies or 0)
                hour_stats[posted_at.hour].append(total)

        ranked = []
        for hour, engagements in hour_stats.items():
            avg = sum(engagements) / len(engagements) if engagements else 0
            ranked.append({"hour": hour, "avg_engagement": round(avg, 1), "post_count": len(engagements)})
        ranked.sort(key=lambda x: x["avg_engagement"], reverse=True)
        return ranked


async def check_hashtag_quota(team_id: str) -> tuple[int, int]:
    """Returns (used, remaining) — 30 unique hashtags per 7 days."""
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    async with AsyncSessionLocal() as session:
        q = (
            select(func.count(func.distinct(HashtagQuotaModel.hashtag)))
            .where(
                HashtagQuotaModel.team_id == team_id,
                HashtagQuotaModel.searched_at >= week_ago,
            )
        )
        result = await session.execute(q)
        used = result.scalar() or 0
        return used, max(0, 30 - used)


# ---------------------------------------------------------------------------
# Team enumeration for scheduler
# ---------------------------------------------------------------------------


async def list_teams_with_social_accounts() -> list[dict]:
    """Returns teams that have at least one monitored IG or Threads account."""
    async with AsyncSessionLocal() as session:
        q = select(BrandSettingsModel).where(
            BrandSettingsModel.team_id.isnot(None)
        )
        result = await session.execute(q)
        teams = []
        for row in result.scalars().all():
            ig = row.instagram_accounts or []
            th = row.threads_accounts or []
            if ig or th:
                teams.append({
                    "team_id": row.team_id,
                    "has_ig": bool(ig),
                    "has_threads": bool(th),
                })
        return teams


async def get_account_collection_stats(
    team_id: str,
) -> list[dict]:
    """Per-account collection stats: post count and last collected timestamp."""
    async with AsyncSessionLocal() as session:
        q = (
            select(
                SocialTrendPostModel.platform,
                SocialTrendPostModel.source_value,
                func.count(SocialTrendPostModel.id).label("post_count"),
                func.max(SocialTrendPostModel.collected_at).label("last_collected"),
            )
            .where(
                SocialTrendPostModel.team_id == team_id,
                SocialTrendPostModel.source_type == "account",
            )
            .group_by(
                SocialTrendPostModel.platform,
                SocialTrendPostModel.source_value,
            )
        )
        result = await session.execute(q)
        return [
            {
                "platform": row.platform,
                "source_value": row.source_value,
                "post_count": row.post_count,
                "last_collected": row.last_collected.isoformat() if row.last_collected else None,
            }
            for row in result.all()
        ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_dict(row: SocialTrendPostModel) -> dict:
    return {
        "id": row.id,
        "team_id": row.team_id,
        "platform": row.platform,
        "source_type": row.source_type,
        "source_value": row.source_value,
        "post_id": row.post_id,
        "author_username": row.author_username,
        "text": row.text,
        "permalink": row.permalink,
        "media_type": row.media_type,
        "thumbnail_url": row.thumbnail_url,
        "hashtags": row.hashtags or [],
        "like_count": row.like_count,
        "comment_count": row.comment_count,
        "share_count": row.share_count,
        "reply_count": row.reply_count,
        "view_count": row.view_count,
        "posted_at": row.posted_at.isoformat() if row.posted_at else None,
        "collected_at": row.collected_at.isoformat() if row.collected_at else None,
    }
