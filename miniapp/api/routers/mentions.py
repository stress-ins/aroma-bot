"""Mentions API — ingest, list, generate replies, publish, ignore."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from bot.services.mentions_store import (
    find_mention_by_external_id,
    get_mention,
    get_token,
    ignore_mention,
    list_mentions,
    list_replies,
    mark_replied,
    mark_reply_published,
    save_mention,
    save_replies,
    select_reply,
)
from ..auth import TeamContext, _require_auth, _require_webhook_auth, _resolve_team_context
from ..models import MentionDetailResponse, MentionIngestPayload, MentionListResponse, MentionReplyResponse, MentionReplySelectPayload

logger = logging.getLogger(__name__)

router = APIRouter()


def _serialize_mention(m, replies=None) -> dict:
    return {
        "mention_id": m.mention_id,
        "platform": m.platform,
        "external_id": m.external_id,
        "type": m.type,
        "author_username": m.author_username,
        "author_name": m.author_name,
        "content": m.content,
        "url": m.url,
        "context_post": m.context_post,
        "received_at": m.received_at.isoformat() if isinstance(m.received_at, datetime) else str(m.received_at),
        "status": m.status,
        "replies": [_serialize_reply(r) for r in (replies or [])],
    }


def _serialize_reply(r) -> dict:
    return {
        "reply_id": r.reply_id,
        "mention_id": r.mention_id,
        "tone": r.tone,
        "content": r.content,
        "generated_at": r.generated_at.isoformat() if isinstance(r.generated_at, datetime) else str(r.generated_at),
        "selected": r.selected,
        "published_at": r.published_at.isoformat() if r.published_at else None,
        "publish_error": r.publish_error,
    }


@router.get("/api/mentions")
async def list_mentions_endpoint(
    platform: str = "all",
    status: str = "pending",
    limit: int = 20,
    offset: int = 0,
    ctx: TeamContext = Depends(_resolve_team_context),
):
    mentions = await list_mentions(platform=platform, status=status, limit=limit, offset=offset, team_id=ctx.team_id)
    items = [_serialize_mention(m) for m in mentions]
    return {"items": items, "total": len(items)}


@router.get("/api/mentions/{mention_id}")
async def get_mention_endpoint(mention_id: str, _: None = Depends(_require_auth)):
    mention = await get_mention(mention_id)
    if not mention:
        raise HTTPException(status_code=404, detail="mention_not_found")
    replies = await list_replies(mention_id)
    return _serialize_mention(mention, replies)


@router.post("/api/mentions/ingest")
async def ingest_mention(payload: MentionIngestPayload, _: None = Depends(_require_webhook_auth)):
    """Called by n8n / Meta webhooks to ingest a new mention from Telegram/Threads/Instagram."""
    mention_id, created = await save_mention(
        platform=payload.platform,
        external_id=payload.external_id,
        type=payload.type,
        author_username=payload.author_username,
        author_name=payload.author_name,
        content=payload.content,
        url=payload.url,
        context_post=payload.context_post,
    )
    if not created:
        return {"mention_id": mention_id, "status": "duplicate"}
    # Fire-and-forget: notify admin via Telegram (if admin_telegram_chat_id configured)
    asyncio.create_task(_notify_admin(mention_id, payload))
    return {"mention_id": mention_id, "status": "created"}


async def _notify_admin(mention_id: str, payload: MentionIngestPayload) -> None:
    from config import settings
    if not settings.admin_telegram_chat_id:
        return
    try:
        import httpx
        preview = payload.content[:80] + ("…" if len(payload.content) > 80 else "")
        miniapp_url = settings.mini_app_url or ""
        text = (
            f"🔔 Новое упоминание · {payload.platform}\n"
            f"@{payload.author_username}: «{preview}»"
        )
        if miniapp_url:
            text += f"\n{miniapp_url}?tab=plans&sub=mentions&id={mention_id}"
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
                json={"chat_id": settings.admin_telegram_chat_id, "text": text},
            )
    except Exception:
        logger.warning("Failed to notify admin about mention %s", mention_id)


@router.post("/api/mentions/{mention_id}/generate-replies")
async def generate_replies_endpoint(mention_id: str, _: None = Depends(_require_auth)):
    mention = await get_mention(mention_id)
    if not mention:
        raise HTTPException(status_code=404, detail="mention_not_found")

    loop = asyncio.get_event_loop()
    from bot.agents.mentions_agent import generate_replies_sync

    replies_data = await loop.run_in_executor(
        None,
        generate_replies_sync,
        mention.content,
        mention.author_username,
        mention.platform,
        mention.context_post,
    )
    saved = await save_replies(mention_id, replies_data)
    return {"replies": [_serialize_reply(r) for r in saved]}


@router.post("/api/mentions/{mention_id}/publish-reply")
async def publish_reply_endpoint(
    mention_id: str,
    payload: MentionReplySelectPayload,
    _: None = Depends(_require_auth),
):
    mention = await get_mention(mention_id)
    if not mention:
        raise HTTPException(status_code=404, detail="mention_not_found")

    replies = await list_replies(mention_id)
    reply = next((r for r in replies if r.reply_id == payload.reply_id), None)
    if not reply:
        raise HTTPException(status_code=404, detail="reply_not_found")

    error = ""
    try:
        await _publish_reply_to_platform(mention, reply.content)
    except Exception as exc:
        error = str(exc)
        logger.error("Failed to publish reply for mention %s: %s", mention_id, exc)

    await mark_reply_published(payload.reply_id, error=error)
    if not error:
        await mark_replied(mention_id)

    return {"reply_id": payload.reply_id, "published": not error, "error": error}


async def _publish_reply_to_platform(mention, content: str) -> None:
    """Publish reply to the platform where the mention occurred."""
    from config import settings

    if mention.platform == "threads":
        from bot.services.threads_api import ThreadsClient
        token_row = await get_token("threads")
        if not token_row:
            raise ValueError("Threads token not configured")
        client = ThreadsClient(token_row.access_token)
        if mention.external_id:
            await asyncio.to_thread(client.publish_text_post, content, reply_to_id=mention.external_id)
        else:
            await asyncio.to_thread(client.publish_text_post, content)
    elif mention.platform == "instagram":
        # Instagram reply — post as comment
        import httpx
        if not mention.external_id:
            raise ValueError("Instagram reply requires external_id")
        # For comment mentions (ig:post_id:comment_id), reply to the media post
        ext_id = mention.external_id
        if ext_id.startswith("ig:"):
            parts = ext_id.split(":")
            media_id = parts[1] if len(parts) >= 2 else ext_id
        else:
            media_id = ext_id
        token_row = await get_token("instagram")
        token = token_row.access_token if token_row else settings.instagram_access_token
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"https://graph.instagram.com/{media_id}/comments",
                params={"message": content, "access_token": token},
            )
            r.raise_for_status()
    elif mention.platform == "youtube":
        if not mention.external_id:
            raise ValueError("YouTube reply requires external_id")
        # For YouTube comment mentions (yt:video_id:comment_id), reply to the comment
        ext_id = mention.external_id
        if ext_id.startswith("yt:"):
            parts = ext_id.split(":")
            comment_id = parts[2] if len(parts) >= 3 else ext_id
        else:
            comment_id = ext_id
        from bot.services.youtube_publisher import reply_to_youtube_comment
        await reply_to_youtube_comment(comment_id, content)
    # telegram: not auto-publishable from here, skip


@router.post("/api/mentions/poll-threads")
async def poll_threads_endpoint(_: None = Depends(_require_auth)):
    """Manually poll Threads API for new mentions and replies."""
    from config import settings
    from bot.services.mentions_poller import poll_threads_mentions

    token_row = await get_token("threads")
    access_token = token_row.access_token if token_row else settings.threads_access_token
    if not access_token:
        raise HTTPException(status_code=400, detail="no_threads_token")

    polled, saved = await poll_threads_mentions(access_token)
    return {"polled": polled, "saved": saved}


@router.post("/api/mentions/poll-comments")
async def poll_comments_endpoint(ctx: TeamContext = Depends(_resolve_team_context)):
    """Poll Instagram + YouTube comments for published reels."""
    from bot.services.comments_poller import poll_published_comments

    polled, saved = await poll_published_comments(team_id=ctx.team_id)
    return {"polled": polled, "saved": saved}


@router.patch("/api/mentions/{mention_id}/ignore")
async def ignore_mention_endpoint(mention_id: str, _: None = Depends(_require_auth)):
    mention = await get_mention(mention_id)
    if not mention:
        raise HTTPException(status_code=404, detail="mention_not_found")
    await ignore_mention(mention_id)
    return {"mention_id": mention_id, "status": "ignored"}
