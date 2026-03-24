"""Playwright-based scraper for public Instagram & Threads profiles.

Fallback collector when Meta Graph API tokens are unavailable or expired.
Scrapes public profile pages to extract recent posts with engagement metrics.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_HASHTAG_RE = re.compile(r"#([\w\u0400-\u04FF]+)")


async def scrape_instagram_profile(username: str, *, max_posts: int = 12) -> list[dict]:
    """Scrape public Instagram profile for recent posts.

    Returns list of dicts with keys:
        post_id, text, permalink, media_type, like_count, comment_count,
        thumbnail_url, hashtags, posted_at, author_username
    """
    from playwright.async_api import async_playwright

    username = username.lstrip("@")
    url = f"https://www.instagram.com/{username}/"
    posts: list[dict] = []

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 900},
                locale="en-US",
            )
            page = await context.new_page()

            # Intercept XHR to capture post data from Instagram's GraphQL
            captured_data: list[dict] = []

            async def _on_response(response):
                try:
                    if "graphql" in response.url or "api/v1/users" in response.url:
                        ct = response.headers.get("content-type", "")
                        if "json" in ct:
                            data = await response.json()
                            captured_data.append(data)
                except Exception:
                    pass

            page.on("response", _on_response)

            await page.goto(url, wait_until="networkidle", timeout=30000)
            # Wait for content to render
            await page.wait_for_timeout(3000)

            # Try to extract from page's shared data or XHR responses
            posts = await _extract_ig_posts_from_page(page, captured_data, username)

            await browser.close()
    except Exception as exc:
        logger.error("Playwright IG scrape failed for @%s: %s", username, exc)

    return posts[:max_posts]


async def _extract_ig_posts_from_page(page, captured_data: list, username: str) -> list[dict]:
    """Extract post data from Instagram page — tries shared data, then XHR, then DOM."""
    posts: list[dict] = []

    # Method 1: Try __additionalData or shared data from script tags
    try:
        shared_data = await page.evaluate("""() => {
            // Try window._sharedData
            if (window._sharedData?.entry_data?.ProfilePage?.[0]?.graphql?.user?.edge_owner_to_timeline_media?.edges) {
                return window._sharedData.entry_data.ProfilePage[0].graphql.user.edge_owner_to_timeline_media.edges;
            }
            // Try __additionalDataLoaded
            for (const key of Object.keys(window)) {
                if (key.startsWith('__additional')) {
                    const val = window[key];
                    if (val?.data?.user?.edge_owner_to_timeline_media?.edges) {
                        return val.data.user.edge_owner_to_timeline_media.edges;
                    }
                }
            }
            return null;
        }""")
        if shared_data:
            for edge in shared_data:
                node = edge.get("node", edge)
                posts.append(_parse_ig_node(node, username))
            if posts:
                return posts
    except Exception:
        pass

    # Method 2: Parse captured XHR data
    for data in captured_data:
        edges = _dig_ig_edges(data)
        if edges:
            for edge in edges:
                node = edge.get("node", edge)
                posts.append(_parse_ig_node(node, username))
            if posts:
                return posts

    # Method 3: DOM scraping — extract post links and basic info
    try:
        post_links = await page.evaluate("""() => {
            const links = document.querySelectorAll('a[href*="/p/"], a[href*="/reel/"]');
            return Array.from(links).slice(0, 12).map(a => {
                const href = a.getAttribute('href');
                const img = a.querySelector('img');
                return {
                    permalink: 'https://www.instagram.com' + href,
                    thumbnail_url: img ? img.src : '',
                    post_id: href.split('/').filter(Boolean).pop() || '',
                };
            });
        }""")
        for link in (post_links or []):
            if link.get("post_id"):
                posts.append({
                    "post_id": link["post_id"],
                    "text": "",
                    "permalink": link["permalink"],
                    "media_type": "IMAGE",
                    "like_count": 0,
                    "comment_count": 0,
                    "thumbnail_url": link.get("thumbnail_url", ""),
                    "hashtags": [],
                    "posted_at": None,
                    "author_username": username,
                })
    except Exception:
        pass

    return posts


def _dig_ig_edges(data: dict) -> list | None:
    """Recursively search for edge_owner_to_timeline_media edges."""
    if isinstance(data, dict):
        if "edge_owner_to_timeline_media" in data:
            return data["edge_owner_to_timeline_media"].get("edges", [])
        for v in data.values():
            result = _dig_ig_edges(v)
            if result:
                return result
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                result = _dig_ig_edges(item)
                if result:
                    return result
    return None


def _parse_ig_node(node: dict, username: str) -> dict:
    """Parse a single Instagram GraphQL node into our format."""
    text = (
        node.get("edge_media_to_caption", {}).get("edges", [{}])[0].get("node", {}).get("text", "")
        if isinstance(node.get("edge_media_to_caption"), dict)
        else node.get("caption", "") or ""
    )
    media_type_map = {
        "GraphImage": "IMAGE",
        "GraphVideo": "VIDEO",
        "GraphSidecar": "CAROUSEL_ALBUM",
    }
    timestamp = node.get("taken_at_timestamp") or node.get("taken_at")
    posted_at = None
    if timestamp:
        try:
            posted_at = datetime.fromtimestamp(int(timestamp), tz=timezone.utc).isoformat()
        except (ValueError, TypeError):
            pass

    return {
        "post_id": node.get("shortcode") or node.get("id") or "",
        "text": text,
        "permalink": f"https://www.instagram.com/p/{node.get('shortcode', '')}/",
        "media_type": media_type_map.get(node.get("__typename"), "IMAGE"),
        "like_count": node.get("edge_media_preview_like", {}).get("count", 0) if isinstance(node.get("edge_media_preview_like"), dict) else 0,
        "comment_count": node.get("edge_media_to_comment", {}).get("count", 0) if isinstance(node.get("edge_media_to_comment"), dict) else 0,
        "thumbnail_url": node.get("thumbnail_src") or node.get("display_url") or "",
        "hashtags": _HASHTAG_RE.findall(text),
        "posted_at": posted_at,
        "author_username": username,
    }


async def scrape_threads_profile(username: str, *, max_posts: int = 20) -> list[dict]:
    """Scrape public Threads profile for recent posts.

    Returns list of dicts with keys:
        post_id, text, permalink, media_type, like_count, reply_count,
        repost_count, hashtags, posted_at, author_username
    """
    from playwright.async_api import async_playwright

    username = username.lstrip("@")
    url = f"https://www.threads.net/@{username}"
    posts: list[dict] = []

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 900},
                locale="en-US",
            )
            page = await context.new_page()

            # Capture API responses
            captured_data: list[dict] = []

            async def _on_response(response):
                try:
                    resp_url = response.url
                    if "api/graphql" in resp_url or "threads" in resp_url:
                        ct = response.headers.get("content-type", "")
                        if "json" in ct:
                            data = await response.json()
                            captured_data.append(data)
                except Exception:
                    pass

            page.on("response", _on_response)

            await page.goto(url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(3000)

            # Scroll to load more posts
            for _ in range(3):
                await page.evaluate("window.scrollBy(0, window.innerHeight)")
                await page.wait_for_timeout(1500)

            # Try to extract from XHR data
            posts = _extract_threads_from_xhr(captured_data, username)

            # Fallback: DOM scraping
            if not posts:
                posts = await _extract_threads_from_dom(page, username)

            await browser.close()
    except Exception as exc:
        logger.error("Playwright Threads scrape failed for @%s: %s", username, exc)

    return posts[:max_posts]


def _extract_threads_from_xhr(captured_data: list, username: str) -> list[dict]:
    """Try to extract Threads posts from captured XHR/GraphQL responses."""
    posts: list[dict] = []

    for data in captured_data:
        # Threads uses various GraphQL response shapes
        threads = _dig_threads_items(data)
        if threads:
            for item in threads:
                post = item.get("post") or item.get("node") or item
                text_obj = post.get("caption") or {}
                text = text_obj.get("text", "") if isinstance(text_obj, dict) else str(text_obj or "")
                code = post.get("code") or post.get("id") or ""

                like_count = 0
                like_obj = post.get("like_count")
                if isinstance(like_obj, int):
                    like_count = like_obj
                elif isinstance(like_obj, dict):
                    like_count = like_obj.get("count", 0)

                posts.append({
                    "post_id": code,
                    "text": text,
                    "permalink": f"https://www.threads.net/@{username}/post/{code}" if code else "",
                    "media_type": "TEXT_POST" if not post.get("image_versions2") else "IMAGE",
                    "like_count": like_count,
                    "reply_count": post.get("text_post_app_info", {}).get("direct_reply_count", 0) if isinstance(post.get("text_post_app_info"), dict) else 0,
                    "share_count": post.get("text_post_app_info", {}).get("repost_count", 0) if isinstance(post.get("text_post_app_info"), dict) else 0,
                    "hashtags": _HASHTAG_RE.findall(text),
                    "posted_at": _ts_to_iso(post.get("taken_at")),
                    "author_username": username,
                })
            if posts:
                return posts

    return posts


def _dig_threads_items(data) -> list | None:
    """Recursively search for threads items in GraphQL responses."""
    if isinstance(data, dict):
        # Look for common Threads data shapes
        for key in ("threads", "items", "edges", "medias"):
            if key in data and isinstance(data[key], list) and data[key]:
                return data[key]
        for v in data.values():
            result = _dig_threads_items(v)
            if result:
                return result
    if isinstance(data, list):
        for item in data:
            result = _dig_threads_items(item)
            if result:
                return result
    return None


async def _extract_threads_from_dom(page, username: str) -> list[dict]:
    """Fallback: extract Threads posts from DOM elements."""
    posts: list[dict] = []

    try:
        items = await page.evaluate("""() => {
            const posts = [];
            // Threads renders posts as divs with data-pressable-container
            const containers = document.querySelectorAll('[data-pressable-container="true"]');
            containers.forEach(el => {
                const linkEl = el.querySelector('a[href*="/post/"]');
                const textEls = el.querySelectorAll('span[dir="auto"]');
                let text = '';
                textEls.forEach(t => { text += t.textContent + ' '; });
                text = text.trim();

                const permalink = linkEl ? linkEl.href : '';
                const code = permalink ? permalink.split('/post/').pop()?.split(/[/?]/).shift() || '' : '';

                if (text || permalink) {
                    posts.push({ post_id: code, text, permalink, author_username: '%s' });
                }
            });

            // Alternative: look for article elements
            if (posts.length === 0) {
                const articles = document.querySelectorAll('article, [role="article"]');
                articles.forEach(el => {
                    const linkEl = el.querySelector('a[href*="/post/"]');
                    const text = el.textContent?.substring(0, 500) || '';
                    const permalink = linkEl ? linkEl.href : '';
                    const code = permalink ? permalink.split('/post/').pop()?.split(/[/?]/).shift() || '' : '';
                    if (code) {
                        posts.push({ post_id: code, text: text.trim(), permalink, author_username: '%s' });
                    }
                });
            }

            return posts.slice(0, 20);
        }""" % (username, username))

        for item in (items or []):
            text = item.get("text", "")
            posts.append({
                "post_id": item.get("post_id", ""),
                "text": text,
                "permalink": item.get("permalink", ""),
                "media_type": "TEXT_POST",
                "like_count": 0,
                "reply_count": 0,
                "share_count": 0,
                "hashtags": _HASHTAG_RE.findall(text),
                "posted_at": None,
                "author_username": username,
            })
    except Exception as exc:
        logger.warning("Threads DOM scraping failed for @%s: %s", username, exc)

    return posts


def _ts_to_iso(ts) -> str | None:
    """Convert unix timestamp to ISO string."""
    if not ts:
        return None
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
    except (ValueError, TypeError):
        return None


async def run_playwright_collection(
    team_id: str,
    instagram_accounts: list[dict],
    threads_accounts: list[dict],
) -> dict:
    """Run Playwright-based collection for a team.

    Collects public posts from monitored accounts and upserts them.
    Returns {"instagram": count, "threads": count}.
    """
    from bot.services.social_trends_store import upsert_social_post

    result = {"instagram": 0, "threads": 0}

    for account in instagram_accounts:
        username = (account.get("username") or "").lstrip("@")
        if not username:
            continue
        try:
            posts = await scrape_instagram_profile(username)
            for p in posts:
                if not p.get("post_id"):
                    continue
                posted_at = None
                if p.get("posted_at"):
                    try:
                        posted_at = datetime.fromisoformat(p["posted_at"])
                    except (ValueError, TypeError):
                        pass
                await upsert_social_post(
                    team_id,
                    "instagram",
                    p["post_id"],
                    source_type="account",
                    source_value=f"@{username}",
                    author_username=p.get("author_username", username),
                    text=p.get("text", ""),
                    permalink=p.get("permalink", ""),
                    media_type=p.get("media_type", "IMAGE"),
                    thumbnail_url=p.get("thumbnail_url", ""),
                    hashtags=p.get("hashtags", []),
                    like_count=p.get("like_count", 0),
                    comment_count=p.get("comment_count", 0),
                    posted_at=posted_at,
                )
                result["instagram"] += 1
            logger.info("Playwright: scraped %d posts from IG @%s", len(posts), username)
        except Exception as exc:
            logger.error("Playwright IG collection failed for @%s: %s", username, exc)

    for account in threads_accounts:
        username = (account.get("username") or "").lstrip("@")
        if not username:
            continue
        try:
            posts = await scrape_threads_profile(username)
            for p in posts:
                if not p.get("post_id"):
                    continue
                posted_at = None
                if p.get("posted_at"):
                    try:
                        posted_at = datetime.fromisoformat(p["posted_at"])
                    except (ValueError, TypeError):
                        pass
                await upsert_social_post(
                    team_id,
                    "threads",
                    p["post_id"],
                    source_type="account",
                    source_value=f"@{username}",
                    author_username=p.get("author_username", username),
                    text=p.get("text", ""),
                    permalink=p.get("permalink", ""),
                    media_type=p.get("media_type", "TEXT_POST"),
                    hashtags=p.get("hashtags", []),
                    like_count=p.get("like_count", 0),
                    reply_count=p.get("reply_count", 0),
                    share_count=p.get("share_count", 0),
                    posted_at=posted_at,
                )
                result["threads"] += 1
            logger.info("Playwright: scraped %d posts from Threads @%s", len(posts), username)
        except Exception as exc:
            logger.error("Playwright Threads collection failed for @%s: %s", username, exc)

    return result
