from __future__ import annotations

import logging
import time

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


class VKCollector(BaseCollector):
    source_name = "ВКонтакте"
    source_key = "vk"
    icon = "🔵"

    async def collect(self) -> SourceResult:
        if not settings.is_source_enabled(self.source_key):
            return SourceResult(
                source_name=self.source_name,
                source_key=self.source_key,
                icon=self.icon,
                error="disabled (нужен VK_TOKEN)",
            )
        try:
            return await self._fetch()
        except Exception as exc:
            logger.exception("VK error")
            return SourceResult(
                source_name=self.source_name,
                source_key=self.source_key,
                icon=self.icon,
                error=str(exc),
            )

    async def _fetch(self) -> SourceResult:
        import vk_api  # type: ignore

        vk_session = vk_api.VkApi(token=settings.vk_token)
        vk = vk_session.get_api()

        start_time = int(time.time()) - 7 * 24 * 3600
        seen: set[str] = set()
        items: list[TrendItem] = []

        for term in _SEARCH_TERMS:
            try:
                resp = vk.newsfeed.search(q=term, count=5, start_time=start_time)
                posts = resp.get("items", [])
                for post in posts:
                    owner_id = post.get("owner_id") or post.get("source_id", 0)
                    post_id = post.get("id", 0)
                    key = f"{owner_id}_{post_id}"
                    if key in seen:
                        continue
                    seen.add(key)

                    text = (post.get("text") or "")[:100].replace("\n", " ")
                    likes = post.get("likes", {}).get("count", 0)
                    views = post.get("views", {}).get("count", 0)
                    url = f"https://vk.com/wall{owner_id}_{post_id}"
                    score = f"❤️{likes}"
                    if views:
                        score += f" 👁{views}"
                    items.append(TrendItem(title=text or "(без текста)", url=url, score=score, extra=term))
            except Exception:
                logger.debug("VK search failed for term: %s", term)

        if not items:
            return SourceResult(
                source_name=self.source_name,
                source_key=self.source_key,
                icon=self.icon,
                error="нет постов",
            )

        return SourceResult(
            source_name=self.source_name,
            source_key=self.source_key,
            icon=self.icon,
            items=items[:10],
        )
