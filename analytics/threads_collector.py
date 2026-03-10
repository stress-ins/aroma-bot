from __future__ import annotations

import asyncio
import logging
import re

from analytics.base import BaseCollector, SourceResult, TrendItem
from keywords.registry import ALL_HASHTAGS_EN

logger = logging.getLogger(__name__)

HASHTAGS = [h.lstrip("#") for h in ALL_HASHTAGS_EN[:6]]
BASE_URL = "https://www.threads.net"


def _parse_post(text: str, url: str) -> TrendItem | None:
    """Parse raw inner_text of a Threads post element."""
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    if len(lines) < 3:
        return None

    username = lines[0]
    # Last lines may be numeric engagement counts — strip them
    body_lines = []
    for line in lines[2:]:
        if re.fullmatch(r"[\d.,KMB]+", line):
            break
        body_lines.append(line)

    post_text = " ".join(body_lines).strip()
    if not post_text or len(post_text) < 10:
        return None

    # Try to extract likes (first number after text)
    numbers = [l for l in lines if re.fullmatch(r"[\d.,KMB]+", l)]
    score = numbers[0] if numbers else "—"

    return TrendItem(
        title=post_text[:120],
        url=url,
        score=f"❤️ {score}",
        extra={"author": username},
    )


async def _fetch_threads(hashtags: list[str]) -> list[TrendItem]:
    from playwright.async_api import async_playwright

    items: list[TrendItem] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        page = await browser.new_page()
        page.set_default_timeout(20_000)

        for tag in hashtags[:3]:  # limit to 3 tags to stay fast
            try:
                await page.goto(f"{BASE_URL}/tag/{tag}", timeout=20_000)
                await page.wait_for_timeout(3_000)

                posts = await page.locator("[data-pressable-container]").all()
                for post in posts[:5]:
                    try:
                        text = await post.inner_text()
                        # Get post permalink
                        link = await post.locator("a[href*='/post/']").first.get_attribute("href")
                        url = f"{BASE_URL}{link}" if link else f"{BASE_URL}/tag/{tag}"
                        item = _parse_post(text, url)
                        if item:
                            items.append(item)
                    except Exception:
                        pass
            except Exception as exc:
                logger.warning("Threads tag %s error: %s", tag, str(exc)[:80])

        await browser.close()

    return items


class ThreadsCollector(BaseCollector):
    source_name = "Threads"
    source_key = "threads"
    icon = "🧵"

    async def collect(self) -> SourceResult:
        try:
            items = await _fetch_threads(HASHTAGS)
            return SourceResult(
                source_name=self.source_name,
                source_key=self.source_key,
                icon=self.icon,
                items=items,
                error="" if items else "Нет результатов",
            )
        except Exception as exc:
            logger.warning("Threads error: %s", exc)
            return SourceResult(
                source_name=self.source_name,
                source_key=self.source_key,
                icon=self.icon,
                error=str(exc)[:120],
            )
