"""Monitor external service status pages via RSS feeds.

Polls Anthropic and Meta status RSS feeds, detects new incidents,
and sends proactive notifications to the admin.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

import httpx

from bot.handlers.monitor import notify_owner_throttled

logger = logging.getLogger(__name__)

_STATUS_FEEDS = [
    {
        "name": "Anthropic Claude",
        "url": "https://status.claude.com/history.rss",
        "emoji": "\U0001f916",
    },
    {
        "name": "Meta (Threads/Instagram)",
        "url": "https://metastatus.com/history.rss",
        "emoji": "\U0001f4f1",
    },
]

_seen_guids: set[str] = set()

_FRESHNESS_HOURS = 24
_HTTP_TIMEOUT = 15


def parse_rss_items(xml_text: str) -> list[dict[str, str]]:
    """Parse RSS XML and return list of items with title, link, pubDate, guid, description."""
    items: list[dict[str, str]] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        logger.warning("Failed to parse RSS XML")
        return items

    for item_el in root.iter("item"):
        item: dict[str, str] = {}
        for field in ("title", "link", "pubDate", "guid", "description"):
            el = item_el.find(field)
            item[field] = (el.text or "").strip() if el is not None else ""
        # Use link as fallback guid
        if not item["guid"]:
            item["guid"] = item["link"]
        items.append(item)
    return items


def filter_fresh_items(
    items: list[dict[str, str]],
    max_age_hours: int = _FRESHNESS_HOURS,
    now: datetime | None = None,
) -> list[dict[str, str]]:
    """Return only items published within the last max_age_hours."""
    if now is None:
        now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=max_age_hours)
    fresh: list[dict[str, str]] = []
    for item in items:
        pub_date_str = item.get("pubDate", "")
        if not pub_date_str:
            continue
        try:
            pub_date = parsedate_to_datetime(pub_date_str)
            if pub_date.tzinfo is None:
                pub_date = pub_date.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue
        if pub_date >= cutoff:
            fresh.append(item)
    return fresh


def _format_notification(feed_name: str, emoji: str, item: dict[str, str]) -> str:
    pub_date = item.get("pubDate", "")
    try:
        dt = parsedate_to_datetime(pub_date)
        pub_date = dt.strftime("%Y-%m-%d %H:%M UTC")
    except (ValueError, TypeError):
        pass
    lines = [
        f"\u26a0\ufe0f {feed_name} — incident",
        "",
        item.get("title", "Unknown"),
        pub_date,
    ]
    link = item.get("link", "")
    if link:
        lines.append("")
        lines.append(link)
    return "\n".join(lines)


async def check_status_feeds() -> None:
    """Poll all status RSS feeds and notify about new incidents."""
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        for feed in _STATUS_FEEDS:
            try:
                resp = await client.get(feed["url"])
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                logger.warning("Failed to fetch %s RSS: %s", feed["name"], exc)
                continue

            items = parse_rss_items(resp.text)
            fresh = filter_fresh_items(items)

            for item in fresh:
                guid = item["guid"]
                if guid in _seen_guids:
                    continue
                _seen_guids.add(guid)
                text = _format_notification(feed["name"], feed["emoji"], item)
                notify_owner_throttled(text, dedup_key=f"status:{guid}", cooldown=3600)
                logger.info("New status incident: %s — %s", feed["name"], item.get("title"))
