"""Direct Meta Graph API publisher for Threads and Instagram.

Uses access tokens stored in PlatformTokenModel (via mentions_store.get_token).
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

THREADS_GRAPH_URL = "https://graph.threads.net/v1.0"
INSTAGRAM_GRAPH_URL = "https://graph.instagram.com/v21.0"


async def _get_token_and_user(platform: str) -> tuple[str, str] | None:
    """Return (access_token, user_id) or None if not configured."""
    from bot.services.mentions_store import get_token

    token_rec = await get_token(platform)
    user_id_rec = await get_token(f"{platform}_user_id")

    if not token_rec or not token_rec.access_token:
        return None
    if not user_id_rec or not user_id_rec.access_token:
        return None

    return token_rec.access_token, user_id_rec.access_token


async def has_direct_token(platform: str) -> bool:
    """Check if a direct Meta token is stored for the given platform."""
    creds = await _get_token_and_user(platform)
    return creds is not None


# ── Threads ────────────────────────────────────────────────────────────────


async def publish_to_threads(
    text: str,
    image_url: str | None = None,
    video_url: str | None = None,
) -> dict[str, Any]:
    """Publish a post to Threads via Graph API.

    Returns {"id": "<post_id>"} on success.
    Raises RuntimeError on failure.
    """
    creds = await _get_token_and_user("threads")
    if not creds:
        raise RuntimeError("threads_token_not_configured")
    access_token, user_id = creds

    async with httpx.AsyncClient(timeout=60) as client:
        # Step 1: Create media container
        container_params: dict[str, Any] = {
            "text": text,
            "access_token": access_token,
        }
        if image_url:
            container_params["media_type"] = "IMAGE"
            container_params["image_url"] = image_url
        elif video_url:
            container_params["media_type"] = "VIDEO"
            container_params["video_url"] = video_url
        else:
            container_params["media_type"] = "TEXT"

        resp = await client.post(
            f"{THREADS_GRAPH_URL}/{user_id}/threads",
            params=container_params,
        )
        _raise_for_meta_error(resp, "Threads container creation")
        container_id = resp.json()["id"]

        # Step 2: Wait for container to be ready (for media posts)
        if image_url or video_url:
            await _wait_for_container(client, container_id, access_token)

        # Step 3: Publish the container
        pub_resp = await client.post(
            f"{THREADS_GRAPH_URL}/{user_id}/threads_publish",
            params={
                "creation_id": container_id,
                "access_token": access_token,
            },
        )
        _raise_for_meta_error(pub_resp, "Threads publish")
        return pub_resp.json()


async def _wait_for_container(
    client: httpx.AsyncClient,
    container_id: str,
    access_token: str,
    max_attempts: int = 10,
    interval: float = 3.0,
) -> None:
    """Poll container status until FINISHED or timeout."""
    for _attempt in range(max_attempts):
        resp = await client.get(
            f"{THREADS_GRAPH_URL}/{container_id}",
            params={"fields": "status,error_message", "access_token": access_token},
        )
        data = resp.json()
        status = data.get("status", "").upper()
        if status == "FINISHED":
            return
        if status in ("ERROR", "EXPIRED"):
            raise RuntimeError(
                f"Threads container failed: {data.get('error_message', status)}"
            )
        await asyncio.sleep(interval)
    raise RuntimeError("Threads container not ready after timeout")


# ── Instagram ──────────────────────────────────────────────────────────────


async def publish_to_instagram(
    caption: str,
    image_url: str | None = None,
    carousel_image_urls: list[str] | None = None,
) -> dict[str, Any]:
    """Publish to Instagram Business via Graph API.

    Supports single image or carousel (multiple images).
    Returns {"id": "<post_id>"} on success.
    Raises RuntimeError on failure.
    """
    creds = await _get_token_and_user("instagram")
    if not creds:
        raise RuntimeError("instagram_token_not_configured")
    access_token, user_id = creds

    async with httpx.AsyncClient(timeout=60) as client:
        if carousel_image_urls and len(carousel_image_urls) > 1:
            return await _publish_instagram_carousel(
                client, user_id, access_token, caption, carousel_image_urls
            )
        elif image_url:
            return await _publish_instagram_single(
                client, user_id, access_token, caption, image_url
            )
        else:
            raise RuntimeError("Instagram requires at least one image")


async def _publish_instagram_single(
    client: httpx.AsyncClient,
    user_id: str,
    access_token: str,
    caption: str,
    image_url: str,
) -> dict[str, Any]:
    resp = await client.post(
        f"{INSTAGRAM_GRAPH_URL}/{user_id}/media",
        params={
            "image_url": image_url,
            "caption": caption,
            "access_token": access_token,
        },
    )
    _raise_for_meta_error(resp, "Instagram media creation")
    container_id = resp.json()["id"]

    pub_resp = await client.post(
        f"{INSTAGRAM_GRAPH_URL}/{user_id}/media_publish",
        params={"creation_id": container_id, "access_token": access_token},
    )
    _raise_for_meta_error(pub_resp, "Instagram publish")
    return pub_resp.json()


async def _publish_instagram_carousel(
    client: httpx.AsyncClient,
    user_id: str,
    access_token: str,
    caption: str,
    image_urls: list[str],
) -> dict[str, Any]:
    # Create individual item containers
    item_ids = []
    for url in image_urls[:10]:  # Instagram max 10
        resp = await client.post(
            f"{INSTAGRAM_GRAPH_URL}/{user_id}/media",
            params={
                "image_url": url,
                "is_carousel_item": "true",
                "access_token": access_token,
            },
        )
        _raise_for_meta_error(resp, "Instagram carousel item")
        item_ids.append(resp.json()["id"])

    # Create carousel container
    carousel_resp = await client.post(
        f"{INSTAGRAM_GRAPH_URL}/{user_id}/media",
        params={
            "media_type": "CAROUSEL",
            "children": ",".join(item_ids),
            "caption": caption,
            "access_token": access_token,
        },
    )
    _raise_for_meta_error(carousel_resp, "Instagram carousel container")
    carousel_id = carousel_resp.json()["id"]

    pub_resp = await client.post(
        f"{INSTAGRAM_GRAPH_URL}/{user_id}/media_publish",
        params={"creation_id": carousel_id, "access_token": access_token},
    )
    _raise_for_meta_error(pub_resp, "Instagram carousel publish")
    return pub_resp.json()


# ── Instagram Reels (Video) ────────────────────────────────────────────────


async def publish_to_instagram_reels(
    caption: str,
    video_url: str,
) -> dict[str, Any]:
    """Publish a video as Instagram Reels via Graph API.

    video_url must be a publicly accessible HTTPS URL.
    Returns {"id": "<post_id>"} on success.
    Raises RuntimeError on failure.
    """
    creds = await _get_token_and_user("instagram")
    if not creds:
        raise RuntimeError("instagram_token_not_configured")
    access_token, user_id = creds

    async with httpx.AsyncClient(timeout=60) as client:
        # Step 1: Create media container for REELS
        resp = await client.post(
            f"{INSTAGRAM_GRAPH_URL}/{user_id}/media",
            params={
                "media_type": "REELS",
                "video_url": video_url,
                "caption": caption,
                "access_token": access_token,
            },
        )
        _raise_for_meta_error(resp, "Instagram Reels container creation")
        container_id = resp.json()["id"]

        # Step 2: Wait for video processing
        await _wait_for_instagram_container(client, container_id, access_token)

        # Step 3: Publish
        pub_resp = await client.post(
            f"{INSTAGRAM_GRAPH_URL}/{user_id}/media_publish",
            params={"creation_id": container_id, "access_token": access_token},
        )
        _raise_for_meta_error(pub_resp, "Instagram Reels publish")
        return pub_resp.json()


async def _wait_for_instagram_container(
    client: httpx.AsyncClient,
    container_id: str,
    access_token: str,
    max_attempts: int = 30,
    interval: float = 5.0,
) -> None:
    """Poll Instagram container status until FINISHED or timeout.

    Instagram uses `status_code` field (not `status` like Threads).
    Video processing can take up to 2-3 minutes.
    """
    for _attempt in range(max_attempts):
        resp = await client.get(
            f"{INSTAGRAM_GRAPH_URL}/{container_id}",
            params={"fields": "status_code,status", "access_token": access_token},
        )
        data = resp.json()
        status_code = str(data.get("status_code", "")).upper()
        if status_code == "FINISHED":
            return
        if status_code in ("ERROR", "EXPIRED"):
            error_msg = data.get("status", "") or status_code
            raise RuntimeError(
                f"Instagram Reels container failed: {error_msg}"
            )
        await asyncio.sleep(interval)
    raise RuntimeError("Instagram Reels container not ready after timeout")


# ── Instagram Comments ────────────────────────────────────────────────────


async def fetch_instagram_comments(post_id: str) -> list[dict[str, Any]]:
    """Fetch comments for an Instagram post via Graph API.

    Returns list of {"id", "text", "username", "timestamp", "like_count"}.
    """
    creds = await _get_token_and_user("instagram")
    if not creds:
        raise RuntimeError("instagram_token_not_configured")
    access_token, _ = creds

    comments: list[dict[str, Any]] = []
    url: str | None = f"{INSTAGRAM_GRAPH_URL}/{post_id}/comments"
    params: dict[str, Any] = {
        "fields": "id,text,username,timestamp,like_count",
        "access_token": access_token,
        "limit": 50,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        while url:
            resp = await client.get(url, params=params)
            if resp.status_code >= 400:
                break
            data = resp.json()
            for item in data.get("data", []):
                comments.append({
                    "id": item.get("id", ""),
                    "text": item.get("text", ""),
                    "username": item.get("username", ""),
                    "timestamp": item.get("timestamp", ""),
                    "like_count": item.get("like_count", 0),
                })
            # Pagination
            paging = data.get("paging", {})
            url = paging.get("next")
            params = {}  # next URL includes all params

    return comments


# ── Insights / Metrics ─────────────────────────────────────────────────────


async def get_threads_insights(post_id: str) -> dict[str, Any]:
    """Fetch engagement insights for a Threads post.

    Returns e.g. {"views": 120, "likes": 5, "replies": 2, "reposts": 1, "quotes": 0}
    """
    creds = await _get_token_and_user("threads")
    if not creds:
        raise RuntimeError("threads_token_not_configured")
    access_token, _ = creds

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{THREADS_GRAPH_URL}/{post_id}/insights",
            params={
                "metric": "views,likes,replies,reposts,quotes",
                "access_token": access_token,
            },
        )
        _raise_for_meta_error(resp, "Threads insights")
        data = resp.json().get("data", [])
        return {item["name"]: item["values"][0]["value"] for item in data if item.get("values")}


async def get_instagram_insights(post_id: str) -> dict[str, Any]:
    """Fetch engagement insights for an Instagram post.

    Combines insights API (impressions, reach) with media fields (likes, comments).
    Returns e.g. {"impressions": 500, "reach": 300, "likes": 20, "comments": 5}
    """
    creds = await _get_token_and_user("instagram")
    if not creds:
        raise RuntimeError("instagram_token_not_configured")
    access_token, _ = creds

    metrics: dict[str, Any] = {}

    async with httpx.AsyncClient(timeout=30) as client:
        # Insights: impressions, reach
        try:
            resp = await client.get(
                f"{INSTAGRAM_GRAPH_URL}/{post_id}/insights",
                params={
                    "metric": "impressions,reach",
                    "access_token": access_token,
                },
            )
            if resp.status_code == 200:
                data = resp.json().get("data", [])
                for item in data:
                    if item.get("values"):
                        metrics[item["name"]] = item["values"][0]["value"]
        except Exception as exc:
            logger.warning("Instagram insights API partial failure: %s", exc)

        # Media fields: like_count, comments_count
        try:
            resp = await client.get(
                f"{INSTAGRAM_GRAPH_URL}/{post_id}",
                params={
                    "fields": "like_count,comments_count",
                    "access_token": access_token,
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                if "like_count" in data:
                    metrics["likes"] = data["like_count"]
                if "comments_count" in data:
                    metrics["comments"] = data["comments_count"]
        except Exception as exc:
            logger.warning("Instagram media fields partial failure: %s", exc)

    if not metrics:
        raise RuntimeError("No Instagram metrics retrieved")
    return metrics


# ── Image URL helpers ──────────────────────────────────────────────────────


def _get_public_image_url(payload: dict[str, Any], kind: str, draft_id: str, media_paths: list[Path]) -> str | None:
    """Get a public URL for the draft's primary image."""
    from config import settings

    base = settings.assets_base_url

    # 1. Single image draft — check payload.image.public_url
    image_info = payload.get("image") or {}
    if isinstance(image_info, dict):
        url = image_info.get("public_url") or ""
        if url and str(url).startswith("http"):
            return str(url)
        internal = image_info.get("url", "")
        if internal and base and str(internal).startswith("/"):
            return f"{base}{internal}"

    # 2. Carousel — use first slide
    slide_images = payload.get("slide_images") or []
    if slide_images and isinstance(slide_images[0], dict):
        url = slide_images[0].get("public_url") or ""
        if url and str(url).startswith("http"):
            return str(url)
        internal = slide_images[0].get("url", "")
        if internal and base and str(internal).startswith("/"):
            return f"{base}{internal}"

    # 3. Fallback: build from local file path
    if media_paths and base:
        local_path = media_paths[0]
        filename = local_path.name
        if local_path.exists():
            if "carousel" in str(local_path):
                return f"{base}/generated/carousel_assets/{draft_id}/{filename}"
            if "reels" in str(local_path):
                return f"{base}/generated/reels_assets/{draft_id}/{filename}"

    return None


def _get_carousel_image_urls(payload: dict[str, Any], draft_id: str, media_paths: list[Path]) -> list[str]:
    """Get list of public URLs for all carousel slides."""
    from config import settings

    base = settings.assets_base_url
    slide_images = payload.get("slide_images") or []
    urls = []

    for item in slide_images:
        if not isinstance(item, dict):
            continue
        url = item.get("public_url") or ""
        if url and str(url).startswith("http"):
            urls.append(str(url))
            continue
        internal = item.get("url", "")
        if internal and base and str(internal).startswith("/"):
            urls.append(f"{base}{internal}")

    return urls


# ── Helpers ────────────────────────────────────────────────────────────────


def _raise_for_meta_error(response: httpx.Response, context: str) -> None:
    try:
        data = response.json()
    except Exception:
        data = {}

    if response.status_code >= 400 or (isinstance(data, dict) and "error" in data):
        err = data.get("error", {}) if isinstance(data, dict) else {}
        msg = err.get("message") or str(data) or response.text[:200]
        code = err.get("code", response.status_code)
        raise RuntimeError(f"{context} failed [{code}]: {msg}")
