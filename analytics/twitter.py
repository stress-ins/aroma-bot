from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from analytics.base import BaseCollector, SourceResult, TrendItem
from config import settings
from keywords.registry import ALL_KEYWORDS_EN

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2)

SEARCH_QUERY = " OR ".join(f'"{kw}"' for kw in ALL_KEYWORDS_EN[:5])


def _fetch_twitter() -> list[TrendItem]:
    import tweepy

    client = tweepy.Client(bearer_token=settings.twitter_bearer_token, wait_on_rate_limit=False)
    query = f"({SEARCH_QUERY}) -is:retweet lang:en"
    resp = client.search_recent_tweets(
        query=query,
        max_results=10,
        tweet_fields=["public_metrics", "created_at", "text"],
        sort_order="relevancy",
    )

    items: list[TrendItem] = []
    if resp.data:
        for tweet in resp.data:
            metrics = tweet.public_metrics or {}
            likes = metrics.get("like_count", 0)
            rt = metrics.get("retweet_count", 0)
            text = tweet.text[:100].replace("\n", " ")
            items.append(TrendItem(
                title=text,
                url=f"https://twitter.com/i/web/status/{tweet.id}",
                score=f"❤️ {likes} | 🔁 {rt}",
            ))
    return items


class TwitterCollector(BaseCollector):
    source_name = "Twitter/X"
    source_key = "twitter"
    icon = "🐦"

    async def collect(self) -> SourceResult:
        if not settings.is_source_enabled("twitter"):
            return SourceResult(
                source_name=self.source_name,
                source_key=self.source_key,
                icon=self.icon,
                error="TWITTER_BEARER_TOKEN не задан",
            )
        try:
            loop = asyncio.get_event_loop()
            items = await loop.run_in_executor(_executor, _fetch_twitter)
            return SourceResult(
                source_name=self.source_name,
                source_key=self.source_key,
                icon=self.icon,
                items=items,
                error="" if items else "Нет результатов",
            )
        except Exception as exc:
            logger.warning("Twitter error: %s", exc)
            return SourceResult(
                source_name=self.source_name,
                source_key=self.source_key,
                icon=self.icon,
                error=str(exc),
            )
