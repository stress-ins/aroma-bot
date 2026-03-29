"""Archive API — CRUD past publications, URL import, bulk import, stats."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException

from bot.services.past_publications_store import (
    bulk_create,
    create_publication,
    delete_publication,
    get_publication,
    get_stats,
    list_publications,
    update_publication,
)
from bot.services.content_analytics import (
    get_format_performance,
    get_pillar_performance,
)
from ..auth import TeamContext, _require_auth, _resolve_team_context
from ..schemas import ArchiveListResponse

logger = logging.getLogger(__name__)

router = APIRouter()


def _serialize(pub) -> dict:
    return pub.to_dict()


# ── List ───────────────────────────────────────────────────────────────────

@router.get("/api/archive", response_model=ArchiveListResponse)
async def list_archive(
    platform: str = "all",
    filter: str = "all",  # all / rated / unrated
    limit: int = 50,
    offset: int = 0,
    ctx: TeamContext = Depends(_resolve_team_context),
):
    pubs = await list_publications(
        ctx.team_id,
        platform=platform if platform != "all" else None,
        rated_only=(filter == "rated"),
        unrated_only=(filter == "unrated"),
        limit=limit,
        offset=offset,
    )
    return {"items": [_serialize(p) for p in pubs], "total": len(pubs)}


# ── Coaching Summary ───────────────────────────────────────────────────────

@router.get("/api/archive/coaching/summary")
async def get_coaching_summary(ctx: TeamContext = Depends(_resolve_team_context)):
    """Get overall coaching summary across all publications."""
    from bot.agents.content_coach import generate_coaching_summary

    pubs = await list_publications(ctx.team_id, limit=100)
    if not pubs:
        return {
            "top_insight": "Нет публикаций для анализа. Добавьте посты в архив.",
            "format_recommendations": [],
            "pillar_recommendations": [],
            "content_gaps": [],
            "weekly_plan_suggestion": "Начните с добавления публикаций в архив.",
        }

    pub_dicts = [_serialize(p) for p in pubs]
    format_perf = await get_format_performance(ctx.team_id)
    pillar_perf = await get_pillar_performance(ctx.team_id)

    summary = await generate_coaching_summary(pub_dicts, format_perf, pillar_perf)
    return summary


# ── Stats ──────────────────────────────────────────────────────────────────

@router.get("/api/archive/stats")
async def archive_stats(ctx: TeamContext = Depends(_resolve_team_context)):
    from bot.services.content_analytics import (
        get_format_performance,
        get_pillar_performance,
        get_top_publications,
    )
    stats = await get_stats(ctx.team_id)
    stats["format_performance"] = await get_format_performance(ctx.team_id)
    stats["pillar_performance"] = await get_pillar_performance(ctx.team_id)
    stats["top_publications"] = await get_top_publications(ctx.team_id)
    return stats


@router.get("/api/archive/tiktok-videos")
async def tiktok_video_stats(ctx: TeamContext = Depends(_resolve_team_context)):
    """Fetch TikTok videos with engagement stats (requires video.list scope)."""
    try:
        from bot.services.tiktok_publisher import fetch_tiktok_videos
        videos = await fetch_tiktok_videos(team_id=ctx.team_id, max_count=20)
        return {"items": videos, "total": len(videos)}
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Detail ─────────────────────────────────────────────────────────────────

@router.get("/api/archive/{pub_id}")
async def get_archive_item(pub_id: str, _: None = Depends(_require_auth)):
    pub = await get_publication(pub_id)
    if not pub:
        raise HTTPException(status_code=404, detail="publication_not_found")
    return _serialize(pub)


# ── Post Coaching ──────────────────────────────────────────────────────────

@router.get("/api/archive/{pub_id}/coaching")
async def get_post_coaching(pub_id: str, ctx: TeamContext = Depends(_resolve_team_context)):
    """Get AI coaching analysis for a specific published post."""
    from bot.agents.content_coach import analyze_post_performance

    pub = await get_publication(pub_id)
    if not pub:
        raise HTTPException(status_code=404, detail="publication_not_found")

    pub_dict = _serialize(pub)

    # Build team averages
    stats = await get_stats(ctx.team_id)
    team_averages = {
        "avg_engagement": stats.get("avg_scores", {}).get("score_engagement", "н/д"),
        "avg_brand": stats.get("avg_scores", {}).get("score_brand_fit", "н/д"),
        "avg_craft": stats.get("avg_scores", {}).get("score_craft", "н/д"),
        "avg_goal": stats.get("avg_scores", {}).get("score_goal_hit", "н/д"),
        "avg_total": stats.get("avg_score", "н/д"),
    }

    format_benchmarks = await get_format_performance(ctx.team_id)
    pillar_benchmarks = await get_pillar_performance(ctx.team_id)

    coaching = await analyze_post_performance(
        pub_dict, team_averages, format_benchmarks, pillar_benchmarks,
    )
    return coaching


# ── Create ─────────────────────────────────────────────────────────────────

@router.post("/api/archive")
async def create_archive_item(body: dict, ctx: TeamContext = Depends(_resolve_team_context)):
    published_at = None
    if body.get("published_at"):
        try:
            published_at = datetime.fromisoformat(body["published_at"])
        except (ValueError, TypeError):
            pass

    pub = await create_publication(
        platform=body.get("platform", "threads"),
        team_id=ctx.team_id,
        created_by=ctx.telegram_id,
        kind=body.get("kind", "text"),
        external_url=body.get("external_url", ""),
        external_id=body.get("external_id", ""),
        topic=body.get("topic", ""),
        caption=body.get("caption", ""),
        hashtags=body.get("hashtags", []),
        published_at=published_at,
        likes=body.get("likes", 0),
        comments=body.get("comments", 0),
        shares=body.get("shares", 0),
        saves=body.get("saves", 0),
        views=body.get("views", 0),
        score_engagement=body.get("score_engagement"),
        score_brand_fit=body.get("score_brand_fit"),
        score_craft=body.get("score_craft"),
        score_goal_hit=body.get("score_goal_hit"),
        content_pillar=body.get("content_pillar", ""),
        funnel_stage=body.get("funnel_stage", ""),
        notes=body.get("notes", ""),
    )
    return _serialize(pub)


# ── Import by URL ──────────────────────────────────────────────────────────

@router.post("/api/archive/import-url")
async def import_from_url(body: dict, ctx: TeamContext = Depends(_resolve_team_context)):
    url = body.get("url", "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="url_required")

    platform = _detect_platform(url)
    if not platform:
        raise HTTPException(status_code=400, detail="unsupported_platform")

    data = await _fetch_post_data(url, platform, ctx.team_id)
    if not data:
        raise HTTPException(status_code=400, detail="could_not_fetch_post")

    data["team_id"] = ctx.team_id
    data["created_by"] = ctx.telegram_id
    pub = await create_publication(**data)
    return _serialize(pub)


# ── Update ─────────────────────────────────────────────────────────────────

@router.put("/api/archive/{pub_id}")
async def update_archive_item(pub_id: str, body: dict, _: None = Depends(_require_auth)):
    published_at_raw = body.pop("published_at", None)
    if published_at_raw is not None:
        try:
            body["published_at"] = datetime.fromisoformat(published_at_raw)
        except (ValueError, TypeError):
            pass

    pub = await update_publication(pub_id, **body)
    if not pub:
        raise HTTPException(status_code=404, detail="publication_not_found")
    return _serialize(pub)


# ── Delete ─────────────────────────────────────────────────────────────────

@router.delete("/api/archive/{pub_id}")
async def delete_archive_item(pub_id: str, _: None = Depends(_require_auth)):
    deleted = await delete_publication(pub_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="publication_not_found")
    return {"ok": True}


# ── Bulk Import ────────────────────────────────────────────────────────────

@router.post("/api/archive/bulk-import")
async def bulk_import(body: dict, ctx: TeamContext = Depends(_resolve_team_context)):
    platform = body.get("platform", "")
    days = body.get("days", 14)
    if platform not in ("threads", "instagram"):
        raise HTTPException(status_code=400, detail="unsupported_platform")

    try:
        posts = await _fetch_recent_posts(platform, ctx.team_id, days)
    except Exception as e:
        logger.exception("bulk_import failed for %s", platform)
        raise HTTPException(status_code=500, detail=str(e)[:200])

    result = await bulk_create(posts, team_id=ctx.team_id, created_by=ctx.telegram_id)
    return {"imported": result["imported"], "skipped": result["skipped"], "errors": []}


# ── Helpers ────────────────────────────────────────────────────────────────

def _detect_platform(url: str) -> str | None:
    url_lower = url.lower()
    if "threads.net" in url_lower:
        return "threads"
    if "instagram.com" in url_lower:
        return "instagram"
    if "t.me" in url_lower or "telegram" in url_lower:
        return "telegram"
    if "tiktok.com" in url_lower:
        return "tiktok"
    return None


def _map_media_type(media_type: str) -> str:
    mapping = {
        "TEXT_POST": "text",
        "IMAGE": "image",
        "VIDEO": "reels",
        "CAROUSEL_ALBUM": "carousel",
        "REELS": "reels",
    }
    return mapping.get(media_type, "text")


async def _fetch_post_data(url: str, platform: str, team_id: str) -> dict | None:
    """Try to fetch post data from API by URL. Returns kwargs for create_publication or None."""
    if platform == "threads":
        return await _fetch_threads_post(url, team_id)
    # Other platforms: return basic stub for manual fill
    return {"platform": platform, "external_url": url, "kind": "text"}


async def _fetch_threads_post(url: str, team_id: str) -> dict | None:
    """Fetch a Threads post by URL using the API."""
    try:
        from bot.services.mentions_store import get_token_for_team
        token_rec = await get_token_for_team("threads", team_id)
        if not token_rec or not token_rec.access_token:
            return {"platform": "threads", "external_url": url, "kind": "text"}

        from bot.services.threads_api import ThreadsClient
        client = ThreadsClient(access_token=token_rec.access_token)
        threads = client.get_threads(limit=50)

        # Try to match by URL
        matched = None
        for t in threads:
            if t.get("permalink") and t["permalink"] in url:
                matched = t
                break
            if url in (t.get("permalink") or ""):
                matched = t
                break

        if not matched:
            return {"platform": "threads", "external_url": url, "kind": "text"}

        published_at = None
        if matched.get("timestamp"):
            try:
                published_at = datetime.fromisoformat(matched["timestamp"].replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass

        # Fetch insights
        metrics = {}
        try:
            from bot.services.meta_publisher import get_threads_insights
            metrics = await get_threads_insights(matched["id"])
        except Exception:
            logger.debug("Could not fetch insights for %s", matched["id"])

        return {
            "platform": "threads",
            "kind": _map_media_type(matched.get("media_type", "TEXT_POST")),
            "external_url": matched.get("permalink", url),
            "external_id": matched["id"],
            "caption": matched.get("text", ""),
            "published_at": published_at,
            "likes": metrics.get("likes", 0),
            "comments": metrics.get("replies", 0),
            "shares": metrics.get("reposts", 0),
            "views": metrics.get("views", 0),
        }
    except Exception:
        logger.debug("Failed to fetch threads post from URL", exc_info=True)
        return {"platform": "threads", "external_url": url, "kind": "text"}


async def _fetch_recent_posts(platform: str, team_id: str, days: int) -> list[dict]:
    """Fetch recent posts from a connected platform account."""
    if platform == "threads":
        return await _fetch_recent_threads(team_id, days)
    if platform == "instagram":
        return await _fetch_recent_instagram(team_id, days)
    return []


async def _fetch_recent_threads(team_id: str, days: int) -> list[dict]:
    from bot.services.mentions_store import get_token_for_team
    token_rec = await get_token_for_team("threads", team_id)
    if not token_rec or not token_rec.access_token:
        raise RuntimeError("Threads не подключён")

    from bot.services.threads_api import ThreadsClient
    client = ThreadsClient(access_token=token_rec.access_token)
    threads = client.get_threads(limit=50)

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # Filter by date first
    filtered = []
    for t in threads:
        published_at = None
        if t.get("timestamp"):
            try:
                published_at = datetime.fromisoformat(t["timestamp"].replace("Z", "+00:00"))
            except (ValueError, TypeError):
                continue
        if published_at and published_at < cutoff:
            continue
        filtered.append((t, published_at))

    # Fetch insights in parallel (max 5 concurrent)
    from bot.services.meta_publisher import get_threads_insights

    sem = asyncio.Semaphore(5)

    async def _get_insights(thread_id: str) -> dict:
        async with sem:
            try:
                return await get_threads_insights(thread_id)
            except Exception:
                logger.debug("Insights failed for thread %s", thread_id)
                return {}

    insight_tasks = [_get_insights(t["id"]) for t, _ in filtered]
    all_metrics = await asyncio.gather(*insight_tasks)

    results = []
    for (t, published_at), metrics in zip(filtered, all_metrics):
        results.append({
            "platform": "threads",
            "kind": _map_media_type(t.get("media_type", "TEXT_POST")),
            "external_url": t.get("permalink", ""),
            "external_id": t["id"],
            "caption": t.get("text", ""),
            "published_at": published_at,
            "likes": metrics.get("likes", 0),
            "comments": metrics.get("replies", 0),
            "shares": metrics.get("reposts", 0),
            "views": metrics.get("views", 0),
        })

    return results


async def _fetch_recent_instagram(team_id: str, days: int) -> list[dict]:
    import httpx
    from bot.services.mentions_store import get_token_for_team

    token_rec = await get_token_for_team("instagram", team_id)
    if not token_rec or not token_rec.access_token:
        raise RuntimeError("Instagram не подключён")

    # Get user_id token
    user_id_rec = await get_token_for_team("instagram_user_id", team_id)
    if not user_id_rec or not user_id_rec.access_token:
        raise RuntimeError("Instagram user_id не найден")

    user_id = user_id_rec.access_token
    access_token = token_rec.access_token
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    async with httpx.AsyncClient(timeout=30) as http:
        resp = await http.get(
            f"https://graph.instagram.com/{user_id}/media",
            params={
                "fields": "id,caption,timestamp,media_type,permalink,like_count,comments_count",
                "limit": 50,
                "access_token": access_token,
            },
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Instagram API error: {resp.status_code}")
        data = resp.json().get("data", [])

    results = []
    for post in data:
        published_at = None
        if post.get("timestamp"):
            try:
                published_at = datetime.fromisoformat(post["timestamp"].replace("Z", "+00:00"))
            except (ValueError, TypeError):
                continue
        if published_at and published_at < cutoff:
            continue

        results.append({
            "platform": "instagram",
            "kind": _map_media_type(post.get("media_type", "IMAGE")),
            "external_url": post.get("permalink", ""),
            "external_id": post["id"],
            "caption": post.get("caption", ""),
            "published_at": published_at,
            "likes": post.get("like_count", 0),
            "comments": post.get("comments_count", 0),
        })

    return results
