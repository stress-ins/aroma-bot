from __future__ import annotations

import asyncio
import logging

from analytics.base import BaseCollector, SourceResult
from analytics.google_trends import GoogleTrendsENCollector, GoogleTrendsRUCollector
from analytics.youtube import YouTubeCollector, YouTubeRUCollector
from analytics.reddit import RedditCollector
from analytics.telegram_channels import TelegramChannelsCollector
from analytics.twitter import TwitterCollector
from analytics.instagram import InstagramCollector, InstagramRUCollector
from analytics.vk import VKCollector
from analytics.wordstat import WordstatCollector
from analytics.tiktok import TikTokCollector, TikTokRUCollector
from analytics.ai_recommendations import get_ai_recommendations

logger = logging.getLogger(__name__)

_BASE_COLLECTORS: list[BaseCollector] = [
    GoogleTrendsENCollector(),
    GoogleTrendsRUCollector(),
    YouTubeCollector(),
    YouTubeRUCollector(),
    RedditCollector(),
    TelegramChannelsCollector(),
    TwitterCollector(),
    InstagramCollector(),
    InstagramRUCollector(),
    VKCollector(),
    WordstatCollector(),
    TikTokCollector(),
    TikTokRUCollector(),
]


async def collect_all() -> list[SourceResult]:
    """Run all collectors concurrently, then get AI recommendations. Never raises."""
    tasks = [c.collect() for c in _BASE_COLLECTORS]
    results: list[SourceResult] = list(await asyncio.gather(*tasks, return_exceptions=False))

    for r in results:
        if not r.ok:
            logger.info("Source %s skipped/failed: %s", r.source_key, r.error or "no items")

    # AI runs last — it receives all other results as context
    ai_result = await get_ai_recommendations(results)
    results.append(ai_result)

    return results
