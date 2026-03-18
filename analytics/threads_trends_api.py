"""Threads Trends Collector — per-team post collection via Graph API.

NOT a BaseCollector. Standalone async service for per-team data collection.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx

from bot.services.social_trends_store import (
    get_best_posting_times,
    get_hashtag_stats,
    get_top_posts,
    upsert_social_post,
)

logger = logging.getLogger(__name__)

GRAPH_URL = "https://graph.threads.net/v1.0"
_MAX_POSTS = 100
_MAX_AGE_DAYS = 30


class ThreadsTrendsCollector:
    """Collects posts from monitored Threads accounts for a single team."""

    def __init__(self, team_id: str, access_token: str, threads_user_id: str):
        self.team_id = team_id
        self._token = access_token
        self._user_id = threads_user_id
        self._request_count = 0

    async def collect_from_accounts(self, accounts: list[dict]) -> int:
        """Collect recent posts from monitored Threads accounts."""
        total = 0
        cutoff = datetime.now(timezone.utc) - timedelta(days=_MAX_AGE_DAYS)

        async with httpx.AsyncClient(timeout=30) as client:
            for account in accounts:
                username = account.get("username", "").lstrip("@")
                threads_user_id = account.get("threads_user_id")
                if not username and not threads_user_id:
                    continue
                try:
                    uid = threads_user_id or self._user_id
                    count = await self._collect_user_threads(client, uid, username, cutoff)
                    total += count
                except Exception as exc:
                    logger.warning(
                        "Threads trends: failed @%s for team %s: %s",
                        username, self.team_id, exc,
                    )
        return total

    async def _collect_user_threads(
        self,
        client: httpx.AsyncClient,
        user_id: str,
        username: str,
        cutoff: datetime,
    ) -> int:
        """Fetch threads for a user, paginating up to _MAX_POSTS."""
        collected = 0
        next_url: str | None = None
        fields = "id,text,timestamp,permalink,username,media_type,like_count,reply_count,repost_count,quotes_count"

        for _page in range(4):  # max 4 pages of 25
            await self._rate_check()
            if next_url:
                resp = await client.get(next_url)
            else:
                resp = await client.get(
                    f"{GRAPH_URL}/{user_id}/threads",
                    params={
                        "fields": fields,
                        "limit": 25,
                        "access_token": self._token,
                    },
                )
            self._request_count += 1

            if resp.status_code != 200:
                _log_api_error(resp, f"Threads user {user_id}")
                break

            data = resp.json()
            posts = data.get("data", [])
            if not posts:
                break

            should_stop = False
            for post in posts:
                posted_at = _parse_timestamp(post.get("timestamp"))
                if posted_at and posted_at < cutoff:
                    should_stop = True
                    continue

                post_username = post.get("username", username)
                await upsert_social_post(
                    team_id=self.team_id,
                    platform="threads",
                    post_id=str(post["id"]),
                    source_type="account",
                    source_value=f"@{post_username}",
                    author_username=post_username,
                    text=post.get("text", ""),
                    permalink=post.get("permalink", ""),
                    media_type=post.get("media_type", ""),
                    like_count=post.get("like_count", 0) or 0,
                    reply_count=post.get("reply_count", 0) or 0,
                    share_count=post.get("repost_count", 0) or 0,
                    comment_count=post.get("quotes_count", 0) or 0,
                    posted_at=posted_at,
                )
                collected += 1

            if should_stop or collected >= _MAX_POSTS:
                break

            paging = data.get("paging", {})
            next_url = paging.get("next")
            if not next_url:
                break

        logger.info(
            "Threads trends: collected %d posts from @%s (team=%s)",
            collected, username, self.team_id,
        )
        return collected

    async def collect_own_insights(self) -> dict:
        """Fetch own account insights (views, likes, replies, reposts)."""
        async with httpx.AsyncClient(timeout=30) as client:
            await self._rate_check()
            resp = await client.get(
                f"{GRAPH_URL}/me/threads_insights",
                params={
                    "metric": "views,likes,replies,reposts,quotes",
                    "period": "day",
                    "access_token": self._token,
                },
            )
            self._request_count += 1
            if resp.status_code != 200:
                _log_api_error(resp, "Threads own insights")
                return {}
            data = resp.json().get("data", [])
            return {
                item["name"]: item.get("total_value", {}).get("value", 0)
                for item in data
                if isinstance(item, dict)
            }

    async def get_summary(self, period_days: int = 7) -> dict:
        """Aggregate summary for the team's Threads data."""
        top_posts = await get_top_posts(self.team_id, "threads", period_days, limit=5)
        hashtag_stats = await get_hashtag_stats(self.team_id, "threads", period_days, limit=10)
        best_times = await get_best_posting_times(self.team_id, "threads", period_days)

        # Extract thread hooks (first line of high-engagement posts)
        thread_hooks = []
        for p in top_posts:
            text = p.get("text", "")
            if text:
                first_line = text.split("\n")[0].strip()
                if first_line:
                    thread_hooks.append(first_line)

        # Avg reply rate
        total_replies = sum(p.get("reply_count", 0) for p in top_posts)
        avg_reply_rate = round(total_replies / len(top_posts), 1) if top_posts else 0

        return {
            "top_posts": top_posts,
            "trending_keywords": hashtag_stats,
            "thread_hooks": thread_hooks[:5],
            "best_times": best_times[:5],
            "avg_reply_rate": avg_reply_rate,
            "platform": "threads",
        }

    async def _rate_check(self) -> None:
        import asyncio
        if self._request_count > 0 and self._request_count % 50 == 0:
            logger.debug("Threads rate check: %d requests, pausing 2s", self._request_count)
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


def _log_api_error(response: httpx.Response, context: str) -> None:
    try:
        data = response.json()
    except Exception:
        data = {}
    err = data.get("error", {}) if isinstance(data, dict) else {}
    msg = err.get("message") or response.text[:200]
    logger.error("%s API error [%d]: %s", context, response.status_code, msg)
