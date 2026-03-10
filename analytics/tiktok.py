from __future__ import annotations

import asyncio
import logging

from analytics.base import BaseCollector, SourceResult, TrendItem
from config import settings

logger = logging.getLogger(__name__)

HASHTAGS_EN = [
    "aromatherapy",
    "soundhealing",
    "gongbath",
    "essentialoils",
    "singingbowls",
]

HASHTAGS_RU = [
    "ароматерапия",
    "звуковыеванны",
    "эфирныемасла",
    "медитация",
    "поющиечаши",
]


def _fmt_plays(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}K"
    return str(n)


async def _fetch_tiktok(hashtags: list[str]) -> list[TrendItem]:
    from TikTokApi import TikTokApi

    raw: list[tuple[int, TrendItem]] = []

    async with TikTokApi() as api:
        await api.create_sessions(
            ms_tokens=[settings.tiktok_ms_token],
            num_sessions=1,
            sleep_after=3,
            headless=True,
        )

        for tag in hashtags:
            try:
                async for video in api.hashtag(name=tag).videos(count=5):
                    d = video.as_dict
                    desc = (d.get("desc") or "")[:80].replace("\n", " ")
                    stats = d.get("stats") or {}
                    plays: int = stats.get("playCount", 0)
                    likes: int = stats.get("diggCount", 0)
                    video_id = d.get("id", "")
                    author = (d.get("author") or {}).get("uniqueId", "_")
                    url = f"https://www.tiktok.com/@{author}/video/{video_id}" if video_id else ""
                    raw.append((plays, TrendItem(
                        title=desc or f"#{tag}",
                        url=url,
                        score=f"▶️ {_fmt_plays(plays)}",
                        extra=f"❤️ {_fmt_plays(likes)} | #{tag}",
                    )))
            except Exception as exc:
                logger.warning("TikTok #%s error: %s", tag, str(exc)[:100])

    raw.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in raw[:10]]


class TikTokCollector(BaseCollector):
    source_name = "TikTok"
    source_key = "tiktok"
    icon = "🎵"

    async def collect(self) -> SourceResult:
        if not settings.is_source_enabled("tiktok"):
            return SourceResult(source_name=self.source_name, source_key=self.source_key,
                                icon=self.icon, error="TIKTOK_MS_TOKEN не задан")
        try:
            items = await _fetch_tiktok(HASHTAGS_EN)
            return SourceResult(source_name=self.source_name, source_key=self.source_key,
                                icon=self.icon, items=items,
                                error="" if items else "Нет результатов")
        except Exception as exc:
            logger.warning("TikTok EN error: %s", exc)
            return SourceResult(source_name=self.source_name, source_key=self.source_key,
                                icon=self.icon, error=str(exc)[:200])


class TikTokRUCollector(BaseCollector):
    source_name = "TikTok RU"
    source_key = "tiktok_ru"
    icon = "🎵"

    async def collect(self) -> SourceResult:
        if not settings.is_source_enabled("tiktok_ru"):
            return SourceResult(source_name=self.source_name, source_key=self.source_key,
                                icon=self.icon, error="TIKTOK_MS_TOKEN не задан")
        try:
            items = await _fetch_tiktok(HASHTAGS_RU)
            return SourceResult(source_name=self.source_name, source_key=self.source_key,
                                icon=self.icon, items=items,
                                error="" if items else "Нет результатов")
        except Exception as exc:
            logger.warning("TikTok RU error: %s", exc)
            return SourceResult(source_name=self.source_name, source_key=self.source_key,
                                icon=self.icon, error=str(exc)[:200])
