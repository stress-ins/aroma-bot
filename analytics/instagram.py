from __future__ import annotations

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta

from analytics.base import BaseCollector, SourceResult, TrendItem
from config import settings

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2)

HASHTAGS_EN = [
    "aromatherapy",
    "soundhealing",
    "gongbath",
    "essentialoils",
    "olfactotherapy",
]

HASHTAGS_RU = [
    "ароматерапия",
    "звуковыеванны",
    "эфирныемасла",
    "медитациягонг",
    "поющиечаши",
]

SESSION_FILE = ".instagrapi_session.json"


def _get_client() -> "instagrapi.Client":
    import instagrapi
    import os
    cl = instagrapi.Client()
    if os.path.exists(SESSION_FILE):
        try:
            cl.load_settings(SESSION_FILE)
            cl.login(settings.instagram_username, settings.instagram_password)
            return cl
        except Exception as exc:
            logger.warning("Instagram session expired (%s), retrying fresh login", str(exc)[:80])
            os.remove(SESSION_FILE)
            cl = instagrapi.Client()
    cl.login(settings.instagram_username, settings.instagram_password)
    cl.dump_settings(SESSION_FILE)
    return cl


def _fetch_instagram(hashtags: list[str]) -> tuple[list[TrendItem], str]:
    cl = _get_client()

    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    items: list[TrendItem] = []
    errors: list[str] = []

    for tag_name in hashtags:
        try:
            medias = cl.hashtag_medias_recent(tag_name, amount=3)
            for media in medias:
                ts = media.taken_at
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if ts < cutoff:
                    continue
                caption = (media.caption_text or "")[:80].replace("\n", " ")
                items.append(TrendItem(
                    title=caption or f"#{tag_name}",
                    url=f"https://instagram.com/p/{media.code}/",
                    score=f"❤️ {media.like_count:,}",
                    extra=f"#{tag_name}",
                ))
        except Exception as exc:
            short = str(exc).split("\n")[0][:120]
            logger.warning("Instagram #%s error: %s", tag_name, short)
            errors.append(f"#{tag_name}: {short}")

        time.sleep(2)

    if not items and errors:
        return [], "; ".join(errors)

    items.sort(key=lambda x: int(x.score.replace("❤️ ", "").replace(",", "")), reverse=True)
    return items[:10], "; ".join(errors) if errors else ""


class InstagramCollector(BaseCollector):
    source_name = "Instagram"
    source_key = "instagram"
    icon = "📸"

    async def collect(self) -> SourceResult:
        if not settings.is_source_enabled("instagram"):
            return SourceResult(source_name=self.source_name, source_key=self.source_key,
                                icon=self.icon, error="INSTAGRAM_USERNAME/PASSWORD не заданы")
        try:
            loop = asyncio.get_event_loop()
            items, err = await loop.run_in_executor(_executor, _fetch_instagram, HASHTAGS_EN)
            return SourceResult(source_name=self.source_name, source_key=self.source_key,
                                icon=self.icon, items=items, error=err)
        except Exception as exc:
            logger.warning("Instagram EN error: %s", exc)
            return SourceResult(source_name=self.source_name, source_key=self.source_key,
                                icon=self.icon, error=str(exc))


class InstagramRUCollector(BaseCollector):
    source_name = "Instagram RU"
    source_key = "instagram_ru"
    icon = "📸"

    async def collect(self) -> SourceResult:
        if not settings.is_source_enabled("instagram"):
            return SourceResult(source_name=self.source_name, source_key=self.source_key,
                                icon=self.icon, error="INSTAGRAM_USERNAME/PASSWORD не заданы")
        try:
            loop = asyncio.get_event_loop()
            items, err = await loop.run_in_executor(_executor, _fetch_instagram, HASHTAGS_RU)
            return SourceResult(source_name=self.source_name, source_key=self.source_key,
                                icon=self.icon, items=items, error=err)
        except Exception as exc:
            logger.warning("Instagram RU error: %s", exc)
            return SourceResult(source_name=self.source_name, source_key=self.source_key,
                                icon=self.icon, error=str(exc))
