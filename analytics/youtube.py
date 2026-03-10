from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from googleapiclient.discovery import build

from analytics.base import BaseCollector, SourceResult, TrendItem
from config import settings

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2)

SEARCH_TERMS_EN = [
    "gong bath meditation",
    "sound healing 2026",
    "aromatherapy essential oils",
    "olfactory therapy",
    "singing bowls meditation",
]

SEARCH_TERMS_RU = [
    "медитация гонг",
    "звуковые ванны",
    "ароматерапия эфирные масла",
    "поющие чаши медитация",
    "ольфактотерапия",
]


def _relative_date(published_at: str) -> str:
    try:
        dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - dt
        if delta.days == 0:
            return "сегодня"
        elif delta.days == 1:
            return "вчера"
        else:
            return f"{delta.days} дн. назад"
    except Exception:
        return published_at[:10]


def _fmt_number(n: int) -> str:
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(n)


def _fetch_youtube(search_terms: list[str], region_code: str = "US",
                   relevance_language: str = "en") -> list[TrendItem]:
    youtube = build("youtube", "v3", developerKey=settings.youtube_api_key)

    seen_ids: set[str] = set()
    video_ids: list[str] = []

    for term in search_terms:
        req = youtube.search().list(
            q=term,
            part="id",
            type="video",
            order="viewCount",
            regionCode=region_code,
            relevanceLanguage=relevance_language,
            publishedAfter=(datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            maxResults=3,
        )
        resp = req.execute()
        for item in resp.get("items", []):
            vid_id = item["id"].get("videoId", "")
            if vid_id and vid_id not in seen_ids:
                seen_ids.add(vid_id)
                video_ids.append(vid_id)

    if not video_ids:
        return []

    stats_resp = youtube.videos().list(
        id=",".join(video_ids[:10]),
        part="snippet,statistics",
    ).execute()

    raw = []
    for v in stats_resp.get("items", []):
        snippet = v.get("snippet", {})
        stats = v.get("statistics", {})
        vid_id = v["id"]
        title = snippet.get("title", "")
        description = snippet.get("description", "")[:500]
        views = int(float(stats.get("viewCount", 0)))
        likes = int(float(stats.get("likeCount", 0)))
        published = _relative_date(snippet.get("publishedAt", ""))
        url = f"https://youtube.com/watch?v={vid_id}"
        raw.append((views, title, description, TrendItem(
            title=title,
            url=url,
            score=f"{_fmt_number(views)} просмотров",
            extra=f"👍 {_fmt_number(likes)} | 📅 {published}",
        )))

    raw.sort(key=lambda x: x[0], reverse=True)
    top = raw[:10]

    # Generate AI summaries if Anthropic key is configured
    if settings.anthropic_api_key and top:
        summaries = _summarize_videos([(title, desc) for _, title, desc, _ in top])
        return [
            TrendItem(
                title=item.title, url=item.url, score=item.score,
                extra=item.extra, summary=summaries.get(i, ""),
            )
            for i, (_, _, _, item) in enumerate(top)
        ]

    return [item for _, _, _, item in top]


def _summarize_videos(videos: list[tuple[str, str]]) -> dict[int, str]:
    """Call Claude once to get Russian summaries for all videos. Returns {index: summary}."""
    try:
        import anthropic

        numbered = "\n".join(
            f"{i}. Название: {title}\nОписание: {desc[:300] or '(нет описания)'}"
            for i, (title, desc) in enumerate(videos)
        )
        prompt = (
            f"Дай краткую выжимку (1-2 предложения на русском) о чём каждое видео.\n"
            f"Ответ строго в формате:\n0. <текст>\n1. <текст>\n...\n\n{numbered}"
        )
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        result: dict[int, str] = {}
        for line in response.content[0].text.strip().splitlines():
            if ". " in line and line[0].isdigit():
                idx_str, _, text = line.partition(". ")
                try:
                    result[int(idx_str)] = text.strip()
                except ValueError:
                    pass
        return result
    except Exception as exc:
        logger.warning("YouTube summary error: %s", exc)
        return {}


class YouTubeCollector(BaseCollector):
    source_name = "YouTube — топ видео"
    source_key = "youtube"
    icon = "▶️"

    async def collect(self) -> SourceResult:
        if not settings.is_source_enabled("youtube"):
            return SourceResult(source_name=self.source_name, source_key=self.source_key,
                                icon=self.icon, error="YOUTUBE_API_KEY не задан")
        try:
            loop = asyncio.get_event_loop()
            items = await loop.run_in_executor(
                _executor, _fetch_youtube, SEARCH_TERMS_EN, "US", "en")
            return SourceResult(source_name=self.source_name, source_key=self.source_key,
                                icon=self.icon, items=items,
                                error="" if items else "Нет результатов")
        except Exception as exc:
            logger.warning("YouTube EN error: %s", exc)
            return SourceResult(source_name=self.source_name, source_key=self.source_key,
                                icon=self.icon, error=str(exc))


class YouTubeRUCollector(BaseCollector):
    source_name = "YouTube RU — топ видео"
    source_key = "youtube_ru"
    icon = "▶️"

    async def collect(self) -> SourceResult:
        if not settings.is_source_enabled("youtube"):
            return SourceResult(source_name=self.source_name, source_key=self.source_key,
                                icon=self.icon, error="YOUTUBE_API_KEY не задан")
        try:
            loop = asyncio.get_event_loop()
            items = await loop.run_in_executor(
                _executor, _fetch_youtube, SEARCH_TERMS_RU, "RU", "ru")
            return SourceResult(source_name=self.source_name, source_key=self.source_key,
                                icon=self.icon, items=items,
                                error="" if items else "Нет результатов")
        except Exception as exc:
            logger.warning("YouTube RU error: %s", exc)
            return SourceResult(source_name=self.source_name, source_key=self.source_key,
                                icon=self.icon, error=str(exc))
