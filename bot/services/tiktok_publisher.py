"""TikTok Content Posting API v2 publisher.

Uses access tokens stored in PlatformTokenModel (via mentions_store.get_token).
Publishes videos via the PULL_FROM_URL upload method.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

TIKTOK_API_BASE = "https://open.tiktokapis.com/v2"
TIKTOK_POST_URL = f"{TIKTOK_API_BASE}/post/publish/video/init/"
TIKTOK_STATUS_URL = f"{TIKTOK_API_BASE}/post/publish/status/fetch/"
TIKTOK_VIDEO_LIST_URL = f"{TIKTOK_API_BASE}/video/list/"

# TikTok caption limit
TIKTOK_CAPTION_MAX_LENGTH = 2200


async def _get_tiktok_token(*, team_id: str | None = None) -> str:
    """Return TikTok access_token or raise RuntimeError if not configured."""
    if team_id:
        from bot.services.mentions_store import get_token_for_team
        token_rec = await get_token_for_team("tiktok", team_id)
    else:
        from bot.services.mentions_store import get_token
        token_rec = await get_token("tiktok")

    if not token_rec or not token_rec.access_token:
        raise RuntimeError("tiktok_token_not_configured")

    return token_rec.access_token


async def publish_to_tiktok(
    caption: str,
    video_url: str,
    *,
    team_id: str | None = None,
) -> dict[str, Any]:
    """Publish video to TikTok via Content Posting API v2.

    Steps:
    1. Get token from PlatformTokenModel
    2. POST init publish with PULL_FROM_URL source
    3. Poll publish status until complete
    4. Return {publish_id, status}

    Raises RuntimeError on failure.
    """
    access_token = await _get_tiktok_token(team_id=team_id)

    truncated_caption = caption[:TIKTOK_CAPTION_MAX_LENGTH] if caption else ""

    async with httpx.AsyncClient(timeout=60) as client:
        # Step 1: Init publish
        resp = await client.post(
            TIKTOK_POST_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json; charset=UTF-8",
            },
            json={
                "post_info": {
                    "title": truncated_caption,
                    "privacy_level": "PUBLIC_TO_EVERYONE",
                    "disable_duet": False,
                    "disable_comment": False,
                    "disable_stitch": False,
                },
                "source_info": {
                    "source": "PULL_FROM_URL",
                    "video_url": video_url,
                },
            },
        )
        _raise_for_tiktok_error(resp, "TikTok publish init")
        data = resp.json().get("data", {})
        publish_id = data.get("publish_id", "")

        if not publish_id:
            raise RuntimeError("TikTok publish init did not return publish_id")

        logger.info("TikTok publish initiated: publish_id=%s", publish_id)

        # Step 2: Poll status
        status = await _poll_publish_status(client, publish_id, access_token)

    return {"publish_id": publish_id, "status": status}


async def get_tiktok_video_status(
    publish_id: str,
    *,
    team_id: str | None = None,
) -> dict[str, Any]:
    """Check TikTok video publish status."""
    access_token = await _get_tiktok_token(team_id=team_id)

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            TIKTOK_STATUS_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json; charset=UTF-8",
            },
            json={"publish_id": publish_id},
        )
        _raise_for_tiktok_error(resp, "TikTok status fetch")
        return resp.json().get("data", {})


async def _poll_publish_status(
    client: httpx.AsyncClient,
    publish_id: str,
    access_token: str,
    max_attempts: int = 30,
    interval: float = 5.0,
) -> str:
    """Poll TikTok publish status until terminal state or timeout.

    Returns final status string.
    """
    for _attempt in range(max_attempts):
        resp = await client.post(
            TIKTOK_STATUS_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json; charset=UTF-8",
            },
            json={"publish_id": publish_id},
        )
        data = resp.json().get("data", {})
        status = data.get("status", "PROCESSING_DOWNLOAD")

        if status == "PUBLISH_COMPLETE":
            logger.info("TikTok publish complete: publish_id=%s", publish_id)
            return status

        if status.startswith("FAILED"):
            fail_reason = data.get("fail_reason", "unknown")
            raise RuntimeError(
                f"TikTok publish failed: status={status}, reason={fail_reason}"
            )

        await asyncio.sleep(interval)

    raise RuntimeError(f"TikTok publish timed out after {max_attempts} attempts")


async def fetch_tiktok_videos(
    *,
    team_id: str | None = None,
    max_count: int = 20,
) -> list[dict]:
    """Fetch user's own TikTok videos with engagement stats.

    Requires `video.list` scope. Returns list of video dicts with:
    id, title, create_time, like_count, comment_count, share_count, view_count.
    """
    access_token = await _get_tiktok_token(team_id=team_id)

    fields = "id,title,create_time,like_count,comment_count,share_count,view_count,video_description"
    videos: list[dict] = []
    cursor: int | None = None
    has_more = True

    async with httpx.AsyncClient(timeout=30) as client:
        while has_more and len(videos) < max_count:
            body: dict = {"max_count": min(20, max_count - len(videos))}
            if cursor is not None:
                body["cursor"] = cursor

            resp = await client.post(
                TIKTOK_VIDEO_LIST_URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json; charset=UTF-8",
                },
                params={"fields": fields},
                json=body,
            )
            _raise_for_tiktok_error(resp, "TikTok video list")

            data = resp.json().get("data", {})
            batch = data.get("videos") or []
            videos.extend(batch)
            has_more = data.get("has_more", False)
            cursor = data.get("cursor")

            if not batch:
                break

    logger.info("Fetched %d TikTok videos", len(videos))
    return videos


def _raise_for_tiktok_error(response: httpx.Response, context: str) -> None:
    """Raise RuntimeError if TikTok API returned an error."""
    try:
        data = response.json()
    except Exception:
        data = {}

    if response.status_code >= 400:
        error = data.get("error", {})
        code = error.get("code", response.status_code)
        message = error.get("message", response.text[:200])
        raise RuntimeError(f"{context} failed [{code}]: {message}")

    # TikTok returns 200 with error in body
    error = data.get("error", {})
    if error.get("code") and error.get("code") != "ok":
        raise RuntimeError(
            f"{context} failed [{error.get('code')}]: {error.get('message', 'unknown error')}"
        )
