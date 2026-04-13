"""Mentions poller — polls Threads API for new mentions and replies.

Extracted from miniapp/api/routers/mentions.py poll_threads_endpoint
so it can be called both from the API and from the scheduler.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from bot.services.mentions_store import (
    find_mention_by_external_id,
    get_own_usernames,
    get_token,
    get_token_for_team,
    list_expiring_tokens,
    save_mention,
    upsert_token,
)
from bot.services.social_trends_store import list_teams_with_social_accounts
from bot.services.threads_api import ThreadsClient
from config import settings

logger = logging.getLogger(__name__)


async def poll_threads_mentions(access_token: str, team_id: str | None = None) -> tuple[int, int]:
    """Poll Threads API for external mentions and replies on own posts.

    Returns (polled, saved). Own posts are NOT ingested as mentions —
    they belong in social trends. Only external mentions (others mentioning
    us) and replies from other users (both on mentions and on own posts)
    are saved.
    """
    loop = asyncio.get_running_loop()
    client = ThreadsClient(access_token=access_token)

    # Determine own usernames to filter out own posts
    own_usernames = await get_own_usernames(team_id)

    # Only fetch external mentions (not own posts)
    raw_items: list[dict] = []
    try:
        items = await loop.run_in_executor(None, client.get_mentions)
        raw_items.extend(items)
    except Exception:
        logger.warning("mentions_poller: get_mentions failed", exc_info=True)

    saved = 0
    for item in raw_items:
        ext_id = item.get("id", "")
        if not ext_id:
            continue

        # Skip own posts
        author = (item.get("username") or "").lower().lstrip("@")
        if author and author in own_usernames:
            continue

        existing = await find_mention_by_external_id("threads", ext_id)
        if existing:
            continue
        await save_mention(
            platform="threads",
            external_id=ext_id,
            type=item.get("media_type", "TEXT"),
            author_username=item.get("username", ""),
            author_name="",
            content=item.get("text", ""),
            url=item.get("permalink", ""),
            context_post=None,
            team_id=team_id,
        )
        saved += 1

        # Also ingest replies from OTHER users for this thread
        try:
            replies = await loop.run_in_executor(None, client.get_replies, ext_id)
            for r in replies:
                r_id = r.get("id", "")
                if not r_id:
                    continue
                # Skip own replies
                reply_author = (r.get("username") or "").lower().lstrip("@")
                if reply_author and reply_author in own_usernames:
                    continue
                if await find_mention_by_external_id("threads", r_id):
                    continue
                await save_mention(
                    platform="threads",
                    external_id=r_id,
                    type="REPLY",
                    author_username=r.get("username", ""),
                    author_name="",
                    content=r.get("text", ""),
                    url=r.get("permalink", ""),
                    context_post=item.get("text", "")[:200],
                    team_id=team_id,
                )
                saved += 1
        except Exception:
            logger.warning("mentions_poller: get_replies failed for %s", ext_id, exc_info=True)

    # --- Poll replies on OWN posts (not just mentions) ---
    try:
        own_posts = await loop.run_in_executor(None, lambda: client.get_threads(limit=15))
        for post in own_posts:
            post_id = post.get("id", "")
            if not post_id:
                continue
            try:
                replies = await loop.run_in_executor(
                    None, lambda pid=post_id: client.get_replies(pid, limit=20),
                )
            except Exception:
                logger.warning("mentions_poller: get_replies failed for own post %s", post_id, exc_info=True)
                continue
            post_text = (post.get("text") or "")[:200]
            for r in replies:
                r_id = r.get("id", "")
                if not r_id:
                    continue
                reply_author = (r.get("username") or "").lower().lstrip("@")
                if reply_author and reply_author in own_usernames:
                    continue
                if await find_mention_by_external_id("threads", r_id):
                    continue
                await save_mention(
                    platform="threads",
                    external_id=r_id,
                    type="REPLY",
                    author_username=r.get("username", ""),
                    author_name="",
                    content=r.get("text", ""),
                    url=r.get("permalink", ""),
                    context_post=post_text,
                    team_id=team_id,
                )
                saved += 1
    except Exception:
        logger.warning("mentions_poller: own-posts replies polling failed", exc_info=True)

    return (len(raw_items), saved)


async def poll_all_teams() -> dict[str, tuple[int, int]]:
    """Iterate teams with social accounts and poll Threads mentions for each.

    Falls back to the global token if no teams are configured.
    Returns {team_id_or_"global": (polled, saved)}.
    """
    results: dict[str, tuple[int, int]] = {}

    teams = await list_teams_with_social_accounts()
    polled_any_team = False

    for team in teams:
        if not team["has_threads"]:
            continue
        team_id = team["team_id"]
        token_row = await get_token_for_team("threads", team_id)
        if not token_row or not token_row.access_token:
            continue
        polled_any_team = True
        try:
            results[team_id] = await poll_threads_mentions(token_row.access_token, team_id)
        except Exception as exc:
            logger.error("Mentions poll failed for team %s: %s", team_id, exc)
            results[team_id] = (0, 0)
        await asyncio.sleep(2)  # pause between teams

    # Global token fallback when no teams polled
    if not polled_any_team:
        token_row = await get_token("threads")
        access_token = token_row.access_token if token_row else settings.threads_access_token
        if access_token:
            try:
                results["global"] = await poll_threads_mentions(access_token)
            except Exception as exc:
                logger.error("Mentions poll (global) failed: %s", exc)
                results["global"] = (0, 0)

    return results


async def _auto_refresh_threads(token) -> str:
    """Auto-refresh Threads long-lived token."""
    import httpx

    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            "https://graph.threads.net/refresh_access_token",
            params={
                "grant_type": "th_refresh_token",
                "access_token": token.access_token,
            },
        )
        r.raise_for_status()
        data = r.json()
    new_token = data["access_token"]
    new_expires = datetime.now(timezone.utc) + timedelta(seconds=data.get("expires_in", 5184000))
    await upsert_token(token.platform, new_token, new_expires)
    return new_token


async def _auto_refresh_instagram(token) -> str:
    """Auto-refresh Instagram long-lived token via ig_refresh_token grant."""
    import httpx

    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            "https://graph.instagram.com/refresh_access_token",
            params={
                "grant_type": "ig_refresh_token",
                "access_token": token.access_token,
            },
        )
        r.raise_for_status()
        data = r.json()
    new_token = data["access_token"]
    new_expires = datetime.now(timezone.utc) + timedelta(seconds=data.get("expires_in", 5184000))
    await upsert_token(token.platform, new_token, new_expires)
    return new_token


async def _auto_refresh_facebook(token) -> str:
    """Auto-refresh Facebook long-lived token via fb_exchange_token grant."""
    from bot.services.social_oauth import refresh_facebook_token

    result = refresh_facebook_token(
        access_token=token.access_token,
        client_id=settings.facebook_app_id,
        client_secret=settings.facebook_app_secret,
    )
    expires_at = None
    if result.get("expires_in"):
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(result["expires_in"]))
    await upsert_token(token.platform, str(result["access_token"]), expires_at)
    return str(result["access_token"])


async def _auto_refresh_canva(token) -> str:
    """Auto-refresh Canva token via refresh_token."""
    from bot.services.social_oauth import refresh_canva_token

    if not token.refresh_token:
        raise ValueError("no refresh_token for Canva")
    result = refresh_canva_token(
        refresh_token=token.refresh_token,
        client_id=settings.canva_client_id,
        client_secret=settings.canva_client_secret,
    )
    expires_at = None
    if result.get("expires_in"):
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(result["expires_in"]))
    await upsert_token(
        token.platform, str(result["access_token"]), expires_at,
        refresh_token=str(result.get("refresh_token", "")),
    )
    return str(result["access_token"])


async def _auto_refresh_youtube(token) -> str:
    """Auto-refresh YouTube token via refresh_token."""
    from bot.services.social_oauth import refresh_youtube_token

    if not token.refresh_token:
        raise ValueError("no refresh_token for YouTube")
    result = refresh_youtube_token(
        refresh_token=token.refresh_token,
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
    )
    expires_at = None
    if result.get("expires_in"):
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(result["expires_in"]))
    await upsert_token(
        token.platform, str(result["access_token"]), expires_at,
        refresh_token=str(result.get("refresh_token", "")),
    )
    return str(result["access_token"])


async def _auto_refresh_tiktok(token) -> str:
    """Auto-refresh TikTok token via refresh_token."""
    from bot.services.social_oauth import refresh_tiktok_token

    if not token.refresh_token:
        raise ValueError("no refresh_token for TikTok")
    result = refresh_tiktok_token(
        refresh_token=token.refresh_token,
        client_key=settings.tiktok_client_key,
        client_secret=settings.tiktok_client_secret,
    )
    expires_at = None
    if result.get("expires_in"):
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(result["expires_in"]))
    await upsert_token(
        token.platform, str(result["access_token"]), expires_at,
        refresh_token=str(result.get("refresh_token", "")),
    )
    return str(result["access_token"])


_AUTO_REFRESH_MAP = {
    "threads": _auto_refresh_threads,
    "instagram": _auto_refresh_instagram,
    "facebook": _auto_refresh_facebook,
    "canva": _auto_refresh_canva,
    "youtube": _auto_refresh_youtube,
    "tiktok": _auto_refresh_tiktok,
}


async def check_expiring_tokens() -> None:
    """Check for tokens expiring within 7 days; auto-refresh all supported platforms, notify owner."""
    import httpx

    expiring = await list_expiring_tokens(days=7)
    if not expiring:
        return

    messages: list[str] = []

    for token in expiring:
        days_left = (token.expires_at - datetime.now(timezone.utc)).days if token.expires_at else 0
        refresh_fn = _AUTO_REFRESH_MAP.get(token.platform)

        if refresh_fn and token.access_token:
            try:
                await refresh_fn(token)
                messages.append(f"✅ {token.platform} token refreshed (was expiring in {days_left}d)")
                logger.info("Token refresh: %s refreshed (was expiring in %dd)", token.platform, days_left)
            except Exception as exc:
                messages.append(f"⚠️ {token.platform} token refresh failed ({days_left}d left): {exc}")
                logger.error("Token refresh failed for %s: %s", token.platform, exc)
        else:
            messages.append(f"⚠️ {token.platform} token expires in {days_left}d — manual refresh needed")

    # Notify owner
    if messages and settings.admin_telegram_chat_id:
        try:
            text = "🔑 Token status:\n" + "\n".join(messages)
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(
                    f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
                    json={"chat_id": settings.admin_telegram_chat_id, "text": text},
                )
        except Exception:
            logger.warning("Failed to notify about expiring tokens")
