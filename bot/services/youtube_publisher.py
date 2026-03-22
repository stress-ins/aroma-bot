"""YouTube video publishing and comment management via YouTube Data API v3.

Uses OAuth2 credentials stored in PlatformTokenModel.
Google API client is synchronous — all calls wrapped in run_in_executor.
"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

MAX_RETRIES = 5
RETRIABLE_STATUS_CODES = (500, 502, 503, 504)


async def _get_youtube_credentials():
    """Build google.oauth2.credentials.Credentials from stored tokens."""
    from bot.services.mentions_store import get_token
    from config import settings

    token_rec = await get_token("youtube")
    if not token_rec or not token_rec.access_token:
        raise RuntimeError("youtube_token_not_configured")

    from google.oauth2.credentials import Credentials

    return Credentials(
        token=token_rec.access_token,
        refresh_token=token_rec.refresh_token or "",
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
    )


def _build_youtube_service(credentials):
    """Build YouTube API service object."""
    from googleapiclient.discovery import build

    return build("youtube", "v3", credentials=credentials)


def _upload_video_sync(
    credentials,
    video_path: Path,
    title: str,
    description: str,
    tags: list[str] | None,
    privacy: str,
    category_id: str,
) -> dict[str, Any]:
    """Synchronous resumable upload with retry."""
    from googleapiclient.http import MediaFileUpload
    from googleapiclient.errors import HttpError

    youtube = _build_youtube_service(credentials)

    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "categoryId": category_id,
            "defaultLanguage": "ru",
            "defaultAudioLanguage": "ru",
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }
    if tags:
        body["snippet"]["tags"] = tags[:30]

    media = MediaFileUpload(
        str(video_path),
        mimetype="video/mp4",
        resumable=True,
        chunksize=10 * 1024 * 1024,
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = None
    retry = 0
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                logger.info("YouTube upload progress: %.1f%%", status.progress() * 100)
        except HttpError as exc:
            if exc.resp.status in RETRIABLE_STATUS_CODES and retry < MAX_RETRIES:
                retry += 1
                sleep_time = random.uniform(0, 2**retry)
                logger.warning(
                    "YouTube upload retry %d/%d after %s (sleeping %.1fs)",
                    retry, MAX_RETRIES, exc.resp.status, sleep_time,
                )
                time.sleep(sleep_time)
            else:
                raise

    video_id = response.get("id", "")
    logger.info("YouTube upload complete: video_id=%s", video_id)
    return {
        "id": video_id,
        "url": f"https://youtu.be/{video_id}",
        "response": response,
    }


async def publish_to_youtube(
    video_path: Path,
    title: str,
    description: str = "",
    tags: list[str] | None = None,
    privacy: str = "public",
    category_id: str = "22",
) -> dict[str, Any]:
    """Upload video to YouTube via Data API v3.

    Args:
        video_path: Local path to video file.
        title: Video title (max 100 chars).
        description: Video description (max 5000 chars).
        tags: List of tags (max 30).
        privacy: public, unlisted, or private.
        category_id: YouTube category (22 = People & Blogs).

    Returns {"id": video_id, "url": "https://youtu.be/..."}.
    """
    if not video_path.exists():
        raise RuntimeError(f"Video file not found: {video_path}")

    credentials = await _get_youtube_credentials()
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        _upload_video_sync,
        credentials,
        video_path,
        title,
        description,
        tags,
        privacy,
        category_id,
    )
    return {"id": result["id"], "url": result["url"]}


# ── Comments ──────────────────────────────────────────────────────────────


def _fetch_comments_sync(credentials, video_id: str) -> list[dict[str, Any]]:
    """Fetch top-level comments for a YouTube video (sync)."""
    youtube = _build_youtube_service(credentials)
    comments: list[dict[str, Any]] = []

    try:
        request = youtube.commentThreads().list(
            part="snippet",
            videoId=video_id,
            maxResults=100,
            textFormat="plainText",
        )
        while request:
            response = request.execute()
            for item in response.get("items", []):
                snippet = item.get("snippet", {}).get("topLevelComment", {}).get("snippet", {})
                comments.append({
                    "id": item.get("id", ""),
                    "text": snippet.get("textDisplay", ""),
                    "author": snippet.get("authorDisplayName", ""),
                    "author_channel": snippet.get("authorChannelId", {}).get("value", ""),
                    "published_at": snippet.get("publishedAt", ""),
                    "like_count": snippet.get("likeCount", 0),
                })
            request = youtube.commentThreads().list_next(request, response)
    except Exception as exc:
        logger.error("Failed to fetch YouTube comments for %s: %s", video_id, exc)

    return comments


async def fetch_youtube_comments(video_id: str) -> list[dict[str, Any]]:
    """Fetch comments for a YouTube video."""
    credentials = await _get_youtube_credentials()
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _fetch_comments_sync, credentials, video_id)


# ── Reply to Comment ──────────────────────────────────────────────────────


def _reply_to_comment_sync(credentials, parent_id: str, text: str) -> dict[str, Any]:
    """Post a reply to a YouTube comment (sync)."""
    youtube = _build_youtube_service(credentials)
    response = youtube.comments().insert(
        part="snippet",
        body={
            "snippet": {
                "parentId": parent_id,
                "textOriginal": text,
            },
        },
    ).execute()
    return {
        "id": response.get("id", ""),
        "text": response.get("snippet", {}).get("textDisplay", ""),
    }


async def reply_to_youtube_comment(parent_id: str, text: str) -> dict[str, Any]:
    """Reply to a YouTube comment."""
    credentials = await _get_youtube_credentials()
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _reply_to_comment_sync, credentials, parent_id, text)
