"""Monitor external service status pages via RSS/Atom feeds.

Polls status RSS feeds for all critical external services,
detects new incidents, and sends proactive notifications to the admin.
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
    {
        "name": "Reddit",
        "url": "https://www.redditstatus.com/history.rss",
        "emoji": "\U0001f4ac",
    },
    {
        "name": "Twitter/X",
        "url": "https://api.twitterstat.us/history.rss",
        "emoji": "\U0001d54f",
    },
    {
        "name": "GitHub (CI/CD)",
        "url": "https://www.githubstatus.com/history.rss",
        "emoji": "\U0001f4bb",
    },
    {
        "name": "Google Cloud (YouTube API)",
        "url": "https://status.cloud.google.com/en/feed.atom",
        "emoji": "\u2601\ufe0f",
        "format": "atom",
    },
]

_seen_guids: set[str] = set()

_FRESHNESS_HOURS = 24
_HTTP_TIMEOUT = 15


def parse_rss_items(xml_text: str, fmt: str = "rss") -> list[dict[str, str]]:
    """Parse RSS or Atom XML and return list of items with title, link, pubDate, guid, description."""
    items: list[dict[str, str]] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        logger.warning("Failed to parse RSS/Atom XML")
        return items

    if fmt == "atom":
        return _parse_atom_entries(root)

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


_ATOM_NS = "{http://www.w3.org/2005/Atom}"


def _parse_atom_entries(root: ET.Element) -> list[dict[str, str]]:
    """Parse Atom feed entries into the same dict format as RSS items."""
    items: list[dict[str, str]] = []
    for entry in root.iter(f"{_ATOM_NS}entry"):
        title_el = entry.find(f"{_ATOM_NS}title")
        link_el = entry.find(f"{_ATOM_NS}link")
        updated_el = entry.find(f"{_ATOM_NS}updated")
        id_el = entry.find(f"{_ATOM_NS}id")
        content_el = entry.find(f"{_ATOM_NS}content")
        if content_el is None:
            content_el = entry.find(f"{_ATOM_NS}summary")

        link = (link_el.get("href", "") if link_el is not None else "").strip()
        guid = (id_el.text or "").strip() if id_el is not None else link
        updated = (updated_el.text or "").strip() if updated_el is not None else ""

        items.append({
            "title": (title_el.text or "").strip() if title_el is not None else "",
            "link": link,
            "pubDate": updated,
            "guid": guid or link,
            "description": (content_el.text or "").strip() if content_el is not None else "",
        })
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
            pub_date = _parse_date(pub_date_str)
        except (ValueError, TypeError):
            continue
        if pub_date >= cutoff:
            fresh.append(item)
    return fresh


def _parse_date(date_str: str) -> datetime:
    """Parse RFC 2822 (RSS) or ISO 8601 (Atom) date strings."""
    try:
        return parsedate_to_datetime(date_str)
    except (ValueError, TypeError):
        pass
    # ISO 8601 fallback (Atom feeds)
    dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _format_notification(feed_name: str, emoji: str, item: dict[str, str]) -> str:
    pub_date = item.get("pubDate", "")
    try:
        dt = _parse_date(pub_date)
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

            fmt = feed.get("format", "rss")
            items = parse_rss_items(resp.text, fmt=fmt)
            fresh = filter_fresh_items(items)

            for item in fresh:
                guid = item["guid"]
                if guid in _seen_guids:
                    continue
                _seen_guids.add(guid)
                text = _format_notification(feed["name"], feed["emoji"], item)
                notify_owner_throttled(text, dedup_key=f"status:{guid}", cooldown=3600)
                logger.info("New status incident: %s — %s", feed["name"], item.get("title"))
