"""Social Trends API — per-team Instagram & Threads analytics."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException

from bot.services.social_trends_store import (
    get_account_collection_stats,
    get_best_posting_times,
    get_content_length_breakdown,
    get_format_breakdown,
    get_hashtag_stats,
    get_posting_heatmap,
    get_top_posts,
    list_social_posts,
)
from ..auth import TeamContext, require_team_role

logger = logging.getLogger(__name__)
router = APIRouter()

# Throttle: 1 manual refresh per team per hour
_last_refresh: dict[str, datetime] = {}
_REFRESH_COOLDOWN = timedelta(hours=1)


@router.get("/api/trends/instagram")
async def trends_instagram(
    period: int = 7,
    ctx: TeamContext = Depends(require_team_role("viewer")),
):
    """Instagram trends for the requesting team."""
    top_posts = await get_top_posts(ctx.team_id, "instagram", period, limit=10)
    hashtag_cloud = await get_hashtag_stats(ctx.team_id, "instagram", period, limit=30)
    heatmap = await get_posting_heatmap(ctx.team_id, "instagram", period)
    format_breakdown = await get_format_breakdown(ctx.team_id, "instagram", period)
    total = await list_social_posts(ctx.team_id, "instagram", limit=1)
    return {
        "top_posts": top_posts,
        "hashtag_cloud": hashtag_cloud,
        "heatmap": heatmap,
        "format_breakdown": format_breakdown,
        "total_posts": len(total),
        "period_days": period,
    }


@router.get("/api/trends/threads")
async def trends_threads(
    period: int = 7,
    ctx: TeamContext = Depends(require_team_role("viewer")),
):
    """Threads trends for the requesting team."""
    top_posts = await get_top_posts(ctx.team_id, "threads", period, limit=10)
    trending_keywords = await get_hashtag_stats(ctx.team_id, "threads", period, limit=20)
    best_times = await get_best_posting_times(ctx.team_id, "threads", period)
    format_breakdown = await get_format_breakdown(ctx.team_id, "threads", period)
    content_lengths = await get_content_length_breakdown(ctx.team_id, period)

    # Extract thread hooks from top posts
    thread_hooks = []
    for p in top_posts:
        text = p.get("text", "")
        if text:
            first_line = text.split("\n")[0].strip()
            if first_line:
                thread_hooks.append(first_line)

    # Repost leaders (posts with highest share_count)
    repost_leaders = sorted(top_posts, key=lambda x: x.get("share_count", 0), reverse=True)[:5]

    # Average reply rate
    total_replies = sum(p.get("reply_count", 0) for p in top_posts)
    avg_reply_rate = round(total_replies / len(top_posts), 1) if top_posts else 0

    return {
        "top_posts": top_posts,
        "trending_keywords": trending_keywords,
        "thread_hooks": thread_hooks[:5],
        "format_breakdown": format_breakdown,
        "content_lengths": content_lengths,
        "best_times": best_times[:10],
        "avg_reply_rate": avg_reply_rate,
        "repost_leaders": repost_leaders,
        "period_days": period,
    }


@router.get("/api/trends/account-stats")
async def trends_account_stats(
    ctx: TeamContext = Depends(require_team_role("viewer")),
):
    """Per-account collection stats: post count and last collected."""
    stats = await get_account_collection_stats(ctx.team_id)
    return {"accounts": stats}


@router.post("/api/trends/refresh")
async def trends_refresh(
    ctx: TeamContext = Depends(require_team_role("editor")),
):
    """Trigger collection for this team only. 1-hour cooldown."""
    now = datetime.now(timezone.utc)
    last = _last_refresh.get(ctx.team_id)
    if last and now - last < _REFRESH_COOLDOWN:
        remaining = int((_REFRESH_COOLDOWN - (now - last)).total_seconds())
        raise HTTPException(
            status_code=429,
            detail={"error": "cooldown", "retry_after_seconds": remaining},
        )

    _last_refresh[ctx.team_id] = now

    import asyncio
    asyncio.create_task(_run_team_collection(ctx.team_id))
    return {"status": "started", "team_id": ctx.team_id}


@router.get("/api/trends/compare")
async def trends_compare(
    period: int = 7,
    ctx: TeamContext = Depends(require_team_role("viewer")),
):
    """Cross-platform comparison for this team."""
    ig_top = await get_top_posts(ctx.team_id, "instagram", period, limit=5)
    th_top = await get_top_posts(ctx.team_id, "threads", period, limit=5)
    ig_times = await get_best_posting_times(ctx.team_id, "instagram", period)
    th_times = await get_best_posting_times(ctx.team_id, "threads", period)

    def _platform_summary(posts, times):
        if not posts:
            return {"avg_engagement": 0, "best_hour": None, "top_topic": None, "post_count": len(posts)}
        total = sum(
            p["like_count"] + p["comment_count"] + p.get("share_count", 0) + p.get("reply_count", 0)
            for p in posts
        )
        return {
            "avg_engagement": round(total / len(posts), 1),
            "best_hour": times[0]["hour"] if times else None,
            "top_topic": posts[0].get("text", "")[:80] if posts else None,
            "post_count": len(posts),
        }

    return {
        "instagram": _platform_summary(ig_top, ig_times),
        "threads": _platform_summary(th_top, th_times),
        "period_days": period,
    }


@router.get("/api/trends/suggestions")
async def trends_suggestions(
    platform: str = "instagram",
    ctx: TeamContext = Depends(require_team_role("viewer")),
):
    """Trending topics, hashtags, hooks, optimal times for the editor sidebar."""
    period = 7
    top_posts = await get_top_posts(ctx.team_id, platform, period, limit=5)
    hashtags = await get_hashtag_stats(ctx.team_id, platform, period, limit=10)
    best_times = await get_best_posting_times(ctx.team_id, platform, period)

    # Build insight cards from top posts
    insights = []
    for p in top_posts:
        text = p.get("text", "")
        if not text:
            continue
        first_line = text.split("\n")[0].strip()
        if not first_line or len(first_line) < 10:
            continue
        engagement = (
            (p.get("like_count") or 0)
            + (p.get("comment_count") or 0)
            + (p.get("share_count") or 0)
            + (p.get("reply_count") or 0)
        )
        media_type = p.get("media_type", "")
        if media_type in ("IMAGE", "CAROUSEL_ALBUM"):
            suggested_format = "carousel"
        elif media_type == "VIDEO":
            suggested_format = "reels"
        elif media_type == "TEXT_POST":
            suggested_format = "threads_series"
        else:
            suggested_format = "content"
        insights.append({
            "topic": first_line[:120],
            "engagement_score": engagement,
            "author_username": p.get("author_username", ""),
            "suggested_format": suggested_format,
            "hashtags": p.get("hashtags", [])[:5],
            "preview": text[:200],
        })

    topics = [ins["topic"] for ins in insights[:5]]

    # Hooks (first lines of highest engagement posts, mostly for Threads)
    hooks = []
    if platform == "threads":
        for p in top_posts:
            text = p.get("text", "")
            if text:
                first_line = text.split("\n")[0].strip()
                if first_line:
                    hooks.append(first_line)

    return {
        "trending_topics": topics[:5],
        "trending_hashtags": [h["tag"] for h in hashtags],
        "hooks": hooks[:5],
        "best_times": best_times[:3],
        "platform": platform,
        "insights": insights[:5],
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _run_team_collection(team_id: str) -> None:
    """Run collection for a single team (used by refresh endpoint)."""
    from bot.services.brand_settings_store import get_brand_settings
    from bot.services.mentions_store import get_token_for_team

    try:
        settings = await get_brand_settings(team_id)
        brand_hashtags = settings.tracked_hashtags or []
        if not brand_hashtags:
            brand_hashtags = ["ароматерапия", "эфирныемасла", "аромамасла"]

        # Determine own username from settings (first account or brand name)
        own_ig_username = ""
        own_th_username = ""
        ig_accounts = settings.instagram_accounts or []
        th_accounts = settings.threads_accounts or []
        if ig_accounts:
            own_ig_username = (ig_accounts[0].get("username") or "").lstrip("@")
        if th_accounts:
            own_th_username = (th_accounts[0].get("username") or "").lstrip("@")

        # Instagram
        ig_token = await get_token_for_team("instagram", team_id)
        ig_uid = await get_token_for_team("instagram_user_id", team_id)
        if ig_token and ig_uid:
            from analytics.instagram_trends import InstagramTrendsCollector

            collector = InstagramTrendsCollector(
                team_id, ig_token.access_token, ig_uid.access_token,
                own_username=own_ig_username,
            )
            if ig_accounts:
                await collector.collect_from_accounts(ig_accounts)
            # Hashtag collection
            await collector.collect_from_hashtags(brand_hashtags)

        # Threads
        th_token = await get_token_for_team("threads", team_id)
        th_uid = await get_token_for_team("threads_user_id", team_id)
        if th_token and th_uid:
            from analytics.threads_trends_api import ThreadsTrendsCollector

            collector = ThreadsTrendsCollector(
                team_id, th_token.access_token, th_uid.access_token,
            )
            await collector.collect_from_accounts(
                th_accounts, own_username=own_th_username,
            )
            # Keyword search — find posts from other users
            await collector.collect_from_keyword_search(brand_hashtags)
            # Post-hoc keyword tagging for already-collected posts
            await collector.tag_posts_by_keywords(brand_hashtags)

        # Playwright fallback: if no API tokens, scrape public profiles
        if not (ig_token and ig_uid) and ig_accounts:
            try:
                from analytics.playwright_scraper import run_playwright_collection

                pw_result = await run_playwright_collection(team_id, ig_accounts, [])
                logger.info("Playwright fallback IG: %d posts for team %s", pw_result["instagram"], team_id)
            except Exception as pw_exc:
                logger.warning("Playwright IG fallback failed for team %s: %s", team_id, pw_exc)

        if not (th_token and th_uid) and th_accounts:
            try:
                from analytics.playwright_scraper import run_playwright_collection

                pw_result = await run_playwright_collection(team_id, [], th_accounts)
                logger.info("Playwright fallback Threads: %d posts for team %s", pw_result["threads"], team_id)
            except Exception as pw_exc:
                logger.warning("Playwright Threads fallback failed for team %s: %s", team_id, pw_exc)

        logger.info("Manual refresh complete for team %s", team_id)
    except Exception as exc:
        logger.error("Manual refresh failed for team %s: %s", team_id, exc)
