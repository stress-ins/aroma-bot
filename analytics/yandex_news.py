from __future__ import annotations

import logging
from urllib.parse import quote

import feedparser
import httpx

from analytics.base import BaseCollector, SourceResult, TrendItem
from config import settings

logger = logging.getLogger(__name__)

_SEARCH_TERMS = [
    "ароматерапия",
    "гонг медитация",
    "звуковое целительство",
    "эфирные масла",
    "ольфактотерапия",
]

_LR = "213"  # Moscow region


class YandexNewsCollector(BaseCollector):
    source_name = "Яндекс.Новости"
    source_key = "yandex_news"
    icon = "🔍"

    async def collect(self) -> SourceResult:
        if not settings.is_source_enabled(self.source_key):
            return SourceResult(
                source_name=self.source_name,
                source_key=self.source_key,
                icon=self.icon,
                error="disabled",
            )
        try:
            return await self._fetch()
        except Exception as exc:
            logger.exception("YandexNews error")
            return SourceResult(
                source_name=self.source_name,
                source_key=self.source_key,
                icon=self.icon,
                error=str(exc),
            )

    async def _fetch(self) -> SourceResult:
        seen_urls: set[str] = set()
        items: list[tuple[str, str, str]] = []  # (published, title, url)

        async with httpx.AsyncClient(timeout=8, follow_redirects=True) as client:
            for term in _SEARCH_TERMS:
                url = f"https://news.yandex.ru/search.rss?text={quote(term)}&lr={_LR}"
                try:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    feed = feedparser.parse(resp.text)
                    for entry in feed.entries:
                        link = getattr(entry, "link", "")
                        if not link or link in seen_urls:
                            continue
                        seen_urls.add(link)
                        title = getattr(entry, "title", "").strip()
                        published = getattr(entry, "published", "")
                        items.append((published, title, link))
                except Exception:
                    logger.debug("Yandex News failed for term: %s", term)

        items.sort(key=lambda x: x[0], reverse=True)

        trend_items = [
            TrendItem(title=title, url=link, extra=pub[:10] if pub else "")
            for pub, title, link in items[:10]
        ]

        if not trend_items:
            return SourceResult(
                source_name=self.source_name,
                source_key=self.source_key,
                icon=self.icon,
                error="нет статей",
            )

        return SourceResult(
            source_name=self.source_name,
            source_key=self.source_key,
            icon=self.icon,
            items=trend_items,
        )
