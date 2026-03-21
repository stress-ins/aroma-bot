"""Lightweight oEmbed clients for Instagram & Threads caption extraction."""

from __future__ import annotations

import logging
import re

import httpx

from config import settings

logger = logging.getLogger(__name__)

_HASHTAG_RE = re.compile(r"#([\w\u0400-\u04FF]+)", re.UNICODE)


async def fetch_instagram_caption(url: str) -> str | None:
    """Fetch post caption via Instagram oEmbed API. Returns None on failure."""
    app_id = settings.instagram_app_id
    app_secret = settings.instagram_app_secret
    if not app_id or not app_secret:
        logger.warning("Instagram oEmbed: app credentials not configured")
        return None

    token = f"{app_id}|{app_secret}"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://graph.facebook.com/v18.0/instagram_oembed",
                params={"url": url, "access_token": token, "maxwidth": 320},
            )
            if resp.status_code != 200:
                logger.debug("Instagram oEmbed %s → HTTP %s", url, resp.status_code)
                return None
            data = resp.json()
            return data.get("title") or ""
    except Exception:
        logger.exception("Instagram oEmbed error for %s", url)
        return None


async def fetch_threads_caption(url: str) -> str | None:
    """Fetch post text via Threads oEmbed API (no auth required)."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://graph.threads.net/threads_oembed",
                params={"url": url},
            )
            if resp.status_code != 200:
                logger.debug("Threads oEmbed %s → HTTP %s", url, resp.status_code)
                return None
            data = resp.json()
            # Threads oEmbed returns HTML; extract text from it
            html = data.get("html", "")
            # The blockquote text contains the post content
            text_match = re.search(
                r'<blockquote[^>]*class="text-post-media"[^>]*>(.*?)</blockquote>',
                html,
                re.DOTALL,
            )
            if text_match:
                # Strip HTML tags
                raw = re.sub(r"<[^>]+>", " ", text_match.group(1))
                return raw.strip()
            # Fallback: author_name may have useful info
            return data.get("author_name") or ""
    except Exception:
        logger.exception("Threads oEmbed error for %s", url)
        return None


def extract_hashtags(text: str) -> list[str]:
    """Extract unique lowercase hashtags from text, preserving order."""
    seen: set[str] = set()
    result: list[str] = []
    for tag in _HASHTAG_RE.findall(text):
        low = tag.lower()
        if low not in seen:
            seen.add(low)
            result.append(low)
    return result
