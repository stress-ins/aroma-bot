"""Poll comments from Instagram and YouTube for published reels drafts.

Comments are saved as mentions in the mentions inbox with the same
flow: generate reply suggestions → select → publish reply.
"""
from __future__ import annotations

import logging
from typing import Any

from bot.services.drafts_store import list_recent_drafts
from bot.services.mentions_store import save_mention, find_mention_by_external_id

logger = logging.getLogger(__name__)


async def poll_published_comments(team_id: str | None = None) -> tuple[int, int]:
    """Poll comments from IG + YT for all published drafts.

    Returns (total_polled, newly_saved).
    """
    drafts = await list_recent_drafts(limit=100, newest_first=True, team_id=team_id)
    published = [d for d in drafts if d.status == "published" and d.kind == "reels_v2"]

    total_polled = 0
    newly_saved = 0

    for draft in published:
        payload = draft.payload or {}
        publish_status = payload.get("publish_status") or []
        if not isinstance(publish_status, list):
            continue

        for entry in publish_status:
            if not isinstance(entry, dict):
                continue
            if entry.get("status") != "success":
                continue

            platform = entry.get("platform", "")
            external_id = entry.get("external_id", "")
            if not external_id:
                continue

            try:
                if platform == "instagram":
                    polled, saved = await _poll_instagram_comments(
                        post_id=external_id,
                        draft_topic=draft.topic or "",
                        team_id=draft.team_id,
                    )
                elif platform == "youtube":
                    polled, saved = await _poll_youtube_comments(
                        video_id=external_id,
                        draft_topic=draft.topic or "",
                        team_id=draft.team_id,
                    )
                else:
                    continue
                total_polled += polled
                newly_saved += saved
            except Exception as exc:
                logger.error(
                    "Failed to poll %s comments for draft %s (ext=%s): %s",
                    platform, draft.draft_id, external_id, exc,
                )

    logger.info(
        "Comments poll complete: total=%d, new=%d, drafts_checked=%d",
        total_polled, newly_saved, len(published),
    )
    return total_polled, newly_saved


async def _poll_instagram_comments(
    post_id: str, draft_topic: str, team_id: str | None,
) -> tuple[int, int]:
    from bot.services.meta_publisher import fetch_instagram_comments

    comments = await fetch_instagram_comments(post_id)
    saved = 0
    for c in comments:
        comment_id = c.get("id", "")
        dedup_id = f"ig:{post_id}:{comment_id}"

        existing = await find_mention_by_external_id("instagram", dedup_id)
        if existing:
            continue

        await save_mention(
            platform="instagram",
            external_id=dedup_id,
            type="comment",
            author_username=c.get("username", ""),
            author_name=c.get("username", ""),
            content=c.get("text", ""),
            url=f"https://www.instagram.com/p/{post_id}/",
            context_post=draft_topic,
            team_id=team_id,
        )
        saved += 1

    return len(comments), saved


async def _poll_youtube_comments(
    video_id: str, draft_topic: str, team_id: str | None,
) -> tuple[int, int]:
    from bot.services.youtube_publisher import fetch_youtube_comments

    comments = await fetch_youtube_comments(video_id)
    saved = 0
    for c in comments:
        comment_id = c.get("id", "")
        dedup_id = f"yt:{video_id}:{comment_id}"

        existing = await find_mention_by_external_id("youtube", dedup_id)
        if existing:
            continue

        await save_mention(
            platform="youtube",
            external_id=dedup_id,
            type="comment",
            author_username=c.get("author", ""),
            author_name=c.get("author", ""),
            content=c.get("text", ""),
            url=f"https://youtu.be/{video_id}",
            context_post=draft_topic,
            team_id=team_id,
        )
        saved += 1

    return len(comments), saved
