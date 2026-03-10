from __future__ import annotations

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor

from pytrends.request import TrendReq

from analytics.base import BaseCollector, SourceResult, TrendItem
from keywords.registry import GOOGLE_TRENDS_KEYWORDS_EN, GOOGLE_TRENDS_KEYWORDS_RU

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2)


def _query(keywords: list[str], hl: str = "en-US", tz: int = 360) -> list[TrendItem]:
    pytrends = TrendReq(hl=hl, tz=tz, timeout=(10, 25))
    pytrends.build_payload(keywords, timeframe="now 7-d")
    df = pytrends.interest_over_time()

    if df is None or df.empty:
        return []

    if "isPartial" in df.columns:
        df = df.drop(columns=["isPartial"])

    items = []
    if len(df) < 2:
        for kw in df.columns:
            avg = int(df[kw].mean())
            items.append(TrendItem(title=kw, score=f"интерес: {avg}/100"))
        return items

    first = df.iloc[0]
    last = df.iloc[-1]
    for kw in df.columns:
        start_val = int(first[kw]) or 1
        end_val = int(last[kw])
        change = round((end_val - start_val) / start_val * 100)
        sign = "+" if change >= 0 else ""
        items.append(TrendItem(
            title=kw,
            score=f"{sign}{change}%",
            extra=f"интерес: {end_val}/100",
        ))

    items.sort(key=lambda x: abs(int(x.score.rstrip("%").lstrip("+") or 0)), reverse=True)
    return items


def _fetch_en() -> list[TrendItem]:
    return _query(GOOGLE_TRENDS_KEYWORDS_EN, hl="en-US", tz=360)


def _fetch_ru() -> list[TrendItem]:
    time.sleep(3)  # avoid rate-limit between the two daily queries
    return _query(GOOGLE_TRENDS_KEYWORDS_RU, hl="ru", tz=180)


class GoogleTrendsENCollector(BaseCollector):
    source_name = "Google Trends EN (7 дней)"
    source_key = "google_trends_en"
    icon = "📈"

    async def collect(self) -> SourceResult:
        try:
            loop = asyncio.get_event_loop()
            items = await loop.run_in_executor(_executor, _fetch_en)
            if not items:
                return SourceResult(source_name=self.source_name, source_key=self.source_key,
                                    icon=self.icon, error="Нет данных")
            return SourceResult(source_name=self.source_name, source_key=self.source_key,
                                icon=self.icon, items=items)
        except Exception as exc:
            logger.warning("GoogleTrends EN error: %s", exc)
            return SourceResult(source_name=self.source_name, source_key=self.source_key,
                                icon=self.icon, error=str(exc))


class GoogleTrendsRUCollector(BaseCollector):
    source_name = "Google Trends RU (7 дней)"
    source_key = "google_trends_ru"
    icon = "📈"

    async def collect(self) -> SourceResult:
        try:
            loop = asyncio.get_event_loop()
            items = await loop.run_in_executor(_executor, _fetch_ru)
            if not items:
                return SourceResult(source_name=self.source_name, source_key=self.source_key,
                                    icon=self.icon, error="Нет данных")
            return SourceResult(source_name=self.source_name, source_key=self.source_key,
                                icon=self.icon, items=items)
        except Exception as exc:
            logger.warning("GoogleTrends RU error: %s", exc)
            return SourceResult(source_name=self.source_name, source_key=self.source_key,
                                icon=self.icon, error=str(exc))
