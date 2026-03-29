from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

import praw

from analytics.base import BaseCollector, SourceResult, TrendItem
from config import settings
from keywords.registry import REDDIT_SUBREDDITS

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2)


def _fetch_reddit() -> list[TrendItem]:
    reddit = praw.Reddit(
        client_id=settings.reddit_client_id,
        client_secret=settings.reddit_client_secret,
        username=settings.reddit_username or None,
        password=settings.reddit_password or None,
        user_agent="AromaTrendsBot/1.0",
    )

    items: list[TrendItem] = []
    for sub_name in REDDIT_SUBREDDITS:
        try:
            sub = reddit.subreddit(sub_name)
            for post in sub.hot(limit=3):
                if post.stickied:
                    continue
                items.append(TrendItem(
                    title=post.title,
                    url=f"https://reddit.com{post.permalink}",
                    score=f"{post.score} 👍",
                    extra=f"r/{sub_name} | 💬 {post.num_comments}",
                ))
        except Exception as exc:
            logger.warning("Reddit subreddit %s error: %s", sub_name, exc)

    items.sort(key=lambda x: int(x.score.split()[0]), reverse=True)
    return items[:10]


class RedditCollector(BaseCollector):
    source_name = "Reddit — горячие обсуждения"
    source_key = "reddit"
    icon = "💬"

    async def collect(self) -> SourceResult:
        if not settings.is_source_enabled("reddit"):
            return SourceResult(
                source_name=self.source_name,
                source_key=self.source_key,
                icon=self.icon,
                error="REDDIT_CLIENT_ID/SECRET не заданы",
            )
        try:
            loop = asyncio.get_running_loop()
            items = await loop.run_in_executor(_executor, _fetch_reddit)
            return SourceResult(
                source_name=self.source_name,
                source_key=self.source_key,
                icon=self.icon,
                items=items,
                error="" if items else "Нет результатов",
            )
        except Exception as exc:
            logger.warning("Reddit error: %s", exc)
            return SourceResult(
                source_name=self.source_name,
                source_key=self.source_key,
                icon=self.icon,
                error=str(exc),
            )
