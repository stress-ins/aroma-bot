"""Instagram Trends Collector — per-team post collection via Graph API.

NOT a BaseCollector (those are global/no team context). This is a standalone
async service that collects per-team, per-post data for analytics.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

import httpx

from bot.services.social_trends_store import (
    check_hashtag_quota,
    get_best_posting_times,
    get_hashtag_stats,
    get_top_posts,
    record_hashtag_search,
    upsert_social_post,
)

logger = logging.getLogger(__name__)

GRAPH_URL = "https://graph.instagram.com/v21.0"
FB_GRAPH_URL = "https://graph.facebook.com/v21.0"
_HASHTAG_RE = re.compile(r"#([\w\u0400-\u04FF]+)")
_MAX_POSTS_PER_ACCOUNT = 25
_MAX_AGE_DAYS = 30


class InstagramTrendsCollector:
    """Collects posts from monitored Instagram accounts for a single team."""

    def __init__(
        self, team_id: str, access_token: str, ig_user_id: str,
        own_username: str = "", fb_token: str = "", fb_user_id: str = "",
    ):
        self.team_id = team_id
        self._token = access_token
        self._user_id = ig_user_id
        self._own_username = own_username.lower().lstrip("@")
        # Facebook Login token for business_discovery + hashtag search
        self._fb_token = fb_token
        self._fb_user_id = fb_user_id
        self._request_count = 0

    async def collect_from_accounts(self, accounts: list[dict]) -> int:
        """Collect recent posts from monitored IG accounts. Returns upserted count."""
        total = 0
        cutoff = datetime.now(timezone.utc) - timedelta(days=_MAX_AGE_DAYS)

        async with httpx.AsyncClient(timeout=30) as client:
            for account in accounts:
                username = account.get("username", "").lstrip("@")
                if not username:
                    continue
                try:
                    count = await self._collect_account(client, username, cutoff)
                    total += count
                except Exception as exc:
                    logger.warning(
                        "IG trends: failed to collect @%s for team %s: %s",
                        username, self.team_id, exc,
                    )
        return total

    async def _collect_account(
        self, client: httpx.AsyncClient, username: str, cutoff: datetime
    ) -> int:
        """Fetch posts for a single account. Uses /me/media for own account,
        business_discovery (FB token preferred) for others, Playwright fallback."""
        if self._own_username and username.lower() == self._own_username:
            return await self._collect_own_media(client, username, cutoff)

        # Try Facebook Login token for business_discovery (has proper permissions)
        if self._fb_token and self._fb_user_id:
            try:
                return await self._collect_via_business_discovery(
                    client, username, cutoff,
                    token=self._fb_token, user_id=self._fb_user_id,
                )
            except RuntimeError as exc:
                logger.warning(
                    "IG trends: FB business_discovery failed for @%s (team=%s): %s — trying IG token",
                    username, self.team_id, exc,
                )

        # Fallback to IG Business Login token
        try:
            return await self._collect_via_business_discovery(client, username, cutoff)
        except RuntimeError as exc:
            logger.warning(
                "IG trends: business_discovery failed for @%s (team=%s): %s — trying Playwright",
                username, self.team_id, exc,
            )
            return await self._collect_via_playwright(username, cutoff)

    async def _collect_via_playwright(self, username: str, cutoff: datetime) -> int:
        """Fallback: scrape public IG profile via Playwright."""
        try:
            from analytics.playwright_scraper import scrape_instagram_profile

            posts = await scrape_instagram_profile(username, max_posts=_MAX_POSTS_PER_ACCOUNT)
            count = 0
            for p in posts:
                if not p.get("post_id"):
                    continue
                posted_at = None
                if p.get("posted_at"):
                    try:
                        posted_at = datetime.fromisoformat(p["posted_at"])
                    except (ValueError, TypeError):
                        pass
                if posted_at and posted_at < cutoff:
                    continue
                caption = p.get("text", "") or ""
                hashtags = _HASHTAG_RE.findall(caption)
                await upsert_social_post(
                    team_id=self.team_id,
                    platform="instagram",
                    post_id=str(p["post_id"]),
                    source_type="account",
                    source_value=f"@{username}",
                    author_username=p.get("author_username", username),
                    text=caption,
                    permalink=p.get("permalink", ""),
                    media_type=p.get("media_type", "IMAGE"),
                    thumbnail_url=p.get("thumbnail_url", ""),
                    hashtags=hashtags,
                    like_count=p.get("like_count", 0),
                    comment_count=p.get("comment_count", 0),
                    posted_at=posted_at,
                )
                count += 1
            logger.info("IG Playwright fallback: collected %d posts from @%s (team=%s)", count, username, self.team_id)
            return count
        except Exception as exc:
            logger.warning("IG Playwright fallback failed for @%s (team=%s): %s", username, self.team_id, exc)
            return 0

    async def _collect_own_media(
        self, client: httpx.AsyncClient, username: str, cutoff: datetime
    ) -> int:
        """Fetch own account posts via GET /{user_id}/media (instagram_business_basic)."""
        await self._rate_check()
        resp = await client.get(
            f"{GRAPH_URL}/{self._user_id}/media",
            params={
                "fields": "id,media_type,media_product_type,thumbnail_url,permalink,caption,like_count,comments_count,timestamp",
                "limit": _MAX_POSTS_PER_ACCOUNT,
                "access_token": self._token,
            },
        )
        self._request_count += 1
        _raise_for_error(resp, f"IG own media @{username}")

        media_data = resp.json().get("data", [])
        return await self._save_posts(media_data, username, cutoff)

    async def _collect_via_business_discovery(
        self, client: httpx.AsyncClient, username: str, cutoff: datetime,
        *, token: str = "", user_id: str = "",
    ) -> int:
        """Fetch posts for another account via business_discovery."""
        effective_token = token or self._token
        effective_uid = user_id or self._user_id
        # FB token works on graph.facebook.com, IG token on graph.instagram.com
        base = FB_GRAPH_URL if token == self._fb_token and self._fb_token else GRAPH_URL
        await self._rate_check()
        resp = await client.get(
            f"{base}/{effective_uid}",
            params={
                "fields": (
                    f"business_discovery.fields("
                    f"username,media.limit({_MAX_POSTS_PER_ACCOUNT})"
                    f"{{id,media_type,media_product_type,thumbnail_url,"
                    f"permalink,caption,like_count,comments_count,timestamp}}"
                    f"){{username={username}}}"
                ),
                "access_token": effective_token,
            },
        )
        self._request_count += 1
        _raise_for_error(resp, f"IG business_discovery @{username}")

        data = resp.json()
        discovery = data.get("business_discovery", {})
        media_data = discovery.get("media", {}).get("data", [])
        return await self._save_posts(media_data, username, cutoff)

    async def _save_posts(
        self, media_data: list[dict], username: str, cutoff: datetime
    ) -> int:
        """Upsert posts from a media data list."""
        count = 0
        for post in media_data:
            posted_at = _parse_timestamp(post.get("timestamp"))
            if posted_at and posted_at < cutoff:
                continue

            caption = post.get("caption", "") or ""
            hashtags = _HASHTAG_RE.findall(caption)

            await upsert_social_post(
                team_id=self.team_id,
                platform="instagram",
                post_id=str(post["id"]),
                source_type="account",
                source_value=f"@{username}",
                author_username=username,
                text=caption,
                permalink=post.get("permalink", ""),
                media_type=post.get("media_type", ""),
                thumbnail_url=post.get("thumbnail_url", ""),
                hashtags=hashtags,
                like_count=post.get("like_count", 0) or 0,
                comment_count=post.get("comments_count", 0) or 0,
                posted_at=posted_at,
            )
            count += 1
        logger.info("IG trends: collected %d posts from @%s (team=%s)", count, username, self.team_id)
        return count

    async def collect_from_hashtags(self, hashtags: list[str]) -> int:
        """Collect posts from hashtag search. Checks quota before each tag."""
        used, remaining = await check_hashtag_quota(self.team_id)
        if remaining <= 0:
            logger.info("IG hashtag quota exhausted for team %s (%d/30)", self.team_id, used)
            return 0

        total = 0
        async with httpx.AsyncClient(timeout=30) as client:
            for tag in hashtags[:remaining]:
                tag_clean = tag.lower().lstrip("#")
                if not tag_clean:
                    continue
                try:
                    count = await self._collect_hashtag(client, tag_clean)
                    await record_hashtag_search(self.team_id, tag_clean)
                    total += count
                except Exception as exc:
                    logger.warning(
                        "IG trends: hashtag #%s failed for team %s: %s",
                        tag_clean, self.team_id, exc,
                    )
        return total

    async def _collect_hashtag(self, client: httpx.AsyncClient, tag: str) -> int:
        """Search hashtag and collect top/recent media. Prefers FB token."""
        # Use Facebook token if available (required for ig_hashtag_search)
        ht_token = self._fb_token or self._token
        ht_uid = self._fb_user_id or self._user_id
        # FB token works on graph.facebook.com, IG token on graph.instagram.com
        base_url = FB_GRAPH_URL if self._fb_token else GRAPH_URL

        # Step 1: Get hashtag ID
        await self._rate_check()
        resp = await client.get(
            f"{base_url}/ig_hashtag_search",
            params={
                "user_id": ht_uid,
                "q": tag,
                "access_token": ht_token,
            },
        )
        self._request_count += 1
        _raise_for_error(resp, f"IG hashtag search #{tag}")
        ht_data = resp.json().get("data", [])
        if not ht_data:
            return 0
        hashtag_id = ht_data[0]["id"]

        # Step 2: Get top + recent media
        count = 0
        for edge in ("top_media", "recent_media"):
            await self._rate_check()
            resp = await client.get(
                f"{base_url}/{hashtag_id}/{edge}",
                params={
                    "user_id": ht_uid,
                    "fields": "id,media_type,permalink,caption,like_count,comments_count,timestamp",
                    "access_token": ht_token,
                },
            )
            self._request_count += 1
            if resp.status_code != 200:
                continue

            for post in resp.json().get("data", []):
                caption = post.get("caption", "") or ""
                hashtags = _HASHTAG_RE.findall(caption)
                posted_at = _parse_timestamp(post.get("timestamp"))

                await upsert_social_post(
                    team_id=self.team_id,
                    platform="instagram",
                    post_id=str(post["id"]),
                    source_type="hashtag",
                    source_value=f"#{tag}",
                    author_username="",
                    text=caption,
                    permalink=post.get("permalink", ""),
                    media_type=post.get("media_type", ""),
                    hashtags=hashtags,
                    like_count=post.get("like_count", 0) or 0,
                    comment_count=post.get("comments_count", 0) or 0,
                    posted_at=posted_at,
                )
                count += 1
        logger.info("IG trends: collected %d posts from #%s (team=%s)", count, tag, self.team_id)
        return count

    async def get_summary(self, period_days: int = 7) -> dict:
        """Aggregate summary for the team's Instagram data."""
        top_posts = await get_top_posts(self.team_id, "instagram", period_days, limit=5)
        hashtag_stats = await get_hashtag_stats(self.team_id, "instagram", period_days, limit=10)
        best_times = await get_best_posting_times(self.team_id, "instagram", period_days)

        # Compute avg engagement
        total_eng = sum(
            p["like_count"] + p["comment_count"] + p.get("share_count", 0)
            for p in top_posts
        )
        avg_eng = round(total_eng / len(top_posts), 1) if top_posts else 0

        return {
            "top_posts": top_posts,
            "top_hashtags": hashtag_stats,
            "best_times": best_times[:5],
            "avg_engagement": avg_eng,
            "platform": "instagram",
        }

    async def _rate_check(self) -> None:
        """Simple rate limiting — pause if approaching 200 requests/hour."""
        import asyncio
        if self._request_count > 0 and self._request_count % 50 == 0:
            logger.debug("IG rate check: %d requests, pausing 2s", self._request_count)
            await asyncio.sleep(2)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_timestamp(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def _raise_for_error(response: httpx.Response, context: str) -> None:
    if response.status_code >= 400:
        try:
            data = response.json()
        except Exception:
            data = {}
        err = data.get("error", {}) if isinstance(data, dict) else {}
        msg = err.get("message") or response.text[:200]
        raise RuntimeError(f"{context} [{response.status_code}]: {msg}")
