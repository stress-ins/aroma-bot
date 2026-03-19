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
        from bot.services.threads_api import post_reply as threads_post_reply
        if mention.external_id:
            await threads_post_reply(mention.external_id, content)
        else:
            # Post as standalone if no parent
            from bot.services.threads_api import post_thread
            await post_thread(content)
    elif mention.platform == "instagram":
        # Instagram reply — post as comment (requires external_id = media_id)
        import httpx
        if not mention.external_id:
            raise ValueError("Instagram reply requires external_id (media_id)")
        token = settings.instagram_access_token
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"https://graph.instagram.com/{mention.external_id}/comments",
                params={"message": content, "access_token": token},
            )
            r.raise_for_status()
    # telegram: not auto-publishable from here, skip


@router.post("/api/mentions/poll-threads")
async def poll_threads_endpoint(_: None = Depends(_require_auth)):
    """Manually poll Threads API for new mentions and replies."""
    from config import settings
    from bot.services.threads_api import ThreadsClient

    token_row = await get_token("threads")
    access_token = token_row.access_token if token_row else settings.threads_access_token
    if not access_token:
        raise HTTPException(status_code=400, detail="no_threads_token")

    client = ThreadsClient(access_token=access_token)

    raw_items: list[dict] = []
    try:
        raw_items.extend(client.get_mentions())
    except Exception:
        logger.warning("poll-threads: get_mentions failed", exc_info=True)
    try:
        raw_items.extend(client.get_threads())
    except Exception:
        logger.warning("poll-threads: get_threads failed", exc_info=True)

    saved = 0
    for item in raw_items:
        ext_id = item.get("id", "")
        if not ext_id:
            continue
        existing = await find_mention_by_external_id("threads", ext_id)
        if existing:
            continue
        await save_mention(
            platform="threads",
            external_id=ext_id,
            type=item.get("media_type", "TEXT"),
            author_username=item.get("username", ""),
            author_name="",
            content=item.get("text", ""),
            url=item.get("permalink", ""),
            context_post=None,
        )
        saved += 1

        # Also ingest replies for this thread
        try:
            replies = client.get_replies(ext_id)
            for r in replies:
                r_id = r.get("id", "")
                if not r_id:
                    continue
                if await find_mention_by_external_id("threads", r_id):
                    continue
                await save_mention(
                    platform="threads",
                    external_id=r_id,
                    type="REPLY",
                    author_username=r.get("username", ""),
                    author_name="",
                    content=r.get("text", ""),
                    url=r.get("permalink", ""),
                    context_post=item.get("text", "")[:200],
                )
                saved += 1
        except Exception:
            logger.warning("poll-threads: get_replies failed for %s", ext_id, exc_info=True)

    return {"polled": len(raw_items), "saved": saved}


@router.patch("/api/mentions/{mention_id}/ignore")
async def ignore_mention_endpoint(mention_id: str, _: None = Depends(_require_auth)):
    mention = await get_mention(mention_id)
    if not mention:
        raise HTTPException(status_code=404, detail="mention_not_found")
    await ignore_mention(mention_id)
    return {"mention_id": mention_id, "status": "ignored"}
