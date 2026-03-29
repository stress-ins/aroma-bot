from __future__ import annotations

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import httpx

from analytics.base import BaseCollector, SourceResult, TrendItem
from config import settings

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=1)

_BASE = "https://api.wordstat.yandex.net"
_TOKEN_URL = "https://oauth.yandex.ru/token"

_token_cache: dict = {"token": "", "expires_at": 0.0}

KEYWORDS = [
    "ароматерапия",
    "звуковые ванны",
    "эфирные масла",
    "медитация",
    "поющие чаши",
]


def _get_token() -> str:
    if time.time() < _token_cache["expires_at"] - 60:
        return _token_cache["token"]
    r = httpx.post(_TOKEN_URL, data={
        "grant_type": "client_credentials",
        "client_id": settings.yandex_client_id,
        "client_secret": settings.yandex_client_secret,
    }, timeout=10)
    r.raise_for_status()
    data = r.json()
    _token_cache["token"] = data["access_token"]
    _token_cache["expires_at"] = time.time() + data["expires_in"]
    return _token_cache["token"]


def _fmt_count(n: int) -> str:
    return f"{n:,}".replace(",", "\u202f")  # narrow no-break space


def _fetch_wordstat() -> list[TrendItem]:
    token = _get_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    today = datetime.now(timezone.utc)
    # dynamics: last 3 full months
    to_date = (today.replace(day=1) - timedelta(days=1))   # last day of previous month
    from_date = (to_date.replace(day=1) - timedelta(days=62)).replace(day=1)  # 3 months back

    raw: list[tuple[int, TrendItem]] = []

    with httpx.Client(timeout=15) as client:
        for keyword in KEYWORDS:
            try:
                # 1. Current search volume
                resp_top = client.post(
                    f"{_BASE}/v1/topRequests",
                    headers=headers,
                    json={"phrase": keyword, "numPhrases": 1, "regions": [225]},
                )
                resp_top.raise_for_status()
                total: int = resp_top.json().get("totalCount", 0)

                time.sleep(0.15)

                # 2. Monthly dynamics for trend calculation
                resp_dyn = client.post(
                    f"{_BASE}/v1/dynamics",
                    headers=headers,
                    json={
                        "phrase": keyword,
                        "regions": [225],
                        "period": "monthly",
                        "fromDate": from_date.strftime("%Y-%m-%d"),
                        "toDate": to_date.strftime("%Y-%m-%d"),
                    },
                )
                resp_dyn.raise_for_status()
                dynamics = resp_dyn.json().get("dynamics", [])

                time.sleep(0.15)

                # Compute trend: last month vs second-to-last
                trend_str = ""
                if len(dynamics) >= 2:
                    prev = dynamics[-2]["count"]
                    last = dynamics[-1]["count"]
                    if prev > 0:
                        pct = round((last - prev) / prev * 100)
                        arrow = "▲" if pct >= 0 else "▼"
                        trend_str = f"{arrow}{abs(pct)}% vs прошлый мес."

                raw.append((total, TrendItem(
                    title=keyword,
                    score=f"{_fmt_count(total)} показов/мес",
                    extra=trend_str,
                )))

            except Exception as exc:
                logger.warning("Wordstat error for '%s': %s", keyword, exc)

    raw.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in raw]


class WordstatCollector(BaseCollector):
    source_name = "Яндекс Wordstat"
    source_key = "wordstat"
    icon = "📊"

    async def collect(self) -> SourceResult:
        if not settings.is_source_enabled("wordstat"):
            return SourceResult(
                source_name=self.source_name, source_key=self.source_key,
                icon=self.icon, error="YANDEX_CLIENT_ID/SECRET не заданы",
            )
        try:
            loop = asyncio.get_running_loop()
            items = await loop.run_in_executor(_executor, _fetch_wordstat)
            return SourceResult(
                source_name=self.source_name, source_key=self.source_key,
                icon=self.icon, items=items,
                error="" if items else "Нет данных",
            )
        except Exception as exc:
            logger.warning("Wordstat collect error: %s", exc)
            return SourceResult(
                source_name=self.source_name, source_key=self.source_key,
                icon=self.icon, error=str(exc),
            )
