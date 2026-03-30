"""Inbox API — Instagram DM conversations and messages."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from bot.services.inbox_store import (
    archive_conversation,
    get_conversation,
    list_conversations,
    list_messages,
    mark_conversation_read,
    save_message,
)
from ..auth import TeamContext, _require_webhook_auth, _resolve_team_context

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Pydantic models ──────────────────────────────────────────────────────────

class InboxReplyPayload(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)


class InboxGenerateReplyPayload(BaseModel):
    tone: str = Field(default="warm")


class InboxIngestPayload(BaseModel):
    platform: str = Field(default="instagram")
    participant_id: str = Field(default="")
    participant_username: str = Field(default="")
    participant_name: str = Field(default="")
    sender_type: str = Field(default="user")
    content: str = Field(default="")
    external_id: str = Field(default="")
    sent_at: str | None = Field(default=None)


# ── Serializers ──────────────────────────────────────────────────────────────

def _serialize_conversation(c) -> dict:
    return {
        "conversation_id": c.conversation_id,
        "platform": c.platform,
        "participant_id": c.participant_id,
        "participant_username": c.participant_username,
        "participant_name": c.participant_name,
        "profile_picture_url": getattr(c, "profile_picture_url", "") or "",
        "last_message_preview": c.last_message_preview,
        "last_message_at": c.last_message_at.isoformat() if isinstance(c.last_message_at, datetime) else str(c.last_message_at or ""),
        "status": c.status,
        "unread_count": c.unread_count,
    }


def _serialize_message(m) -> dict:
    return {
        "message_id": m.message_id,
        "conversation_id": m.conversation_id,
        "sender_type": m.sender_type,
        "content": m.content,
        "sent_at": m.sent_at.isoformat() if isinstance(m.sent_at, datetime) else str(m.sent_at),
        "external_id": m.external_id,
    }


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/api/inbox")
async def list_inbox(
    status: str = "active",
    limit: int = 20,
    offset: int = 0,
    ctx: TeamContext = Depends(_resolve_team_context),
):
    """List conversations."""
    conversations = await list_conversations(
        team_id=ctx.team_id, status=status, limit=limit, offset=offset
    )
    items = [_serialize_conversation(c) for c in conversations]
    return {"items": items, "total": len(items)}


@router.get("/api/inbox/{conversation_id}")
async def get_inbox_conversation(
    conversation_id: str,
    ctx: TeamContext = Depends(_resolve_team_context),
):
    """Get conversation with messages."""
    conv = await get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="conversation_not_found")
    if conv.team_id and conv.team_id != ctx.team_id:
        raise HTTPException(status_code=403, detail="team_mismatch")

    # Mark as read
    await mark_conversation_read(conversation_id)

    messages = await list_messages(conversation_id)
    result = _serialize_conversation(conv)
    result["messages"] = [_serialize_message(m) for m in messages]
    return result


@router.post("/api/inbox/{conversation_id}/reply")
async def reply_to_conversation(
    conversation_id: str,
    payload: InboxReplyPayload,
    ctx: TeamContext = Depends(_resolve_team_context),
):
    """Send a reply to a conversation."""
    conv = await get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="conversation_not_found")
    if conv.team_id and conv.team_id != ctx.team_id:
        raise HTTPException(status_code=403, detail="team_mismatch")

    # Send via Instagram API
    error = ""
    try:
        await _send_instagram_message(conv.participant_id, payload.text, ctx.team_id)
    except Exception as exc:
        error = str(exc)
        logger.error("Failed to send DM to %s: %s", conv.participant_id, exc)

    # Save outgoing message locally
    message_id, _ = await save_message(
        conversation_id=conversation_id,
        sender_type="business",
        content=payload.text,
    )

    return {"message_id": message_id, "sent": not error, "error": error}


@router.post("/api/inbox/{conversation_id}/generate-reply")
async def generate_inbox_reply(
    conversation_id: str,
    ctx: TeamContext = Depends(_resolve_team_context),
):
    """Generate AI reply suggestions for a DM conversation."""
    conv = await get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="conversation_not_found")
    if conv.team_id and conv.team_id != ctx.team_id:
        raise HTTPException(status_code=403, detail="team_mismatch")

    messages = await list_messages(conversation_id, limit=10)
    # Build context from recent messages
    context_lines = []
    for m in messages[-5:]:
        role = "Клиент" if m.sender_type == "user" else "Мы"
        context_lines.append(f"{role}: {m.content}")
    conversation_context = "\n".join(context_lines)

    loop = asyncio.get_running_loop()
    from bot.agents.mentions_agent import generate_replies_sync

    last_user_msg = ""
    for m in reversed(messages):
        if m.sender_type == "user":
            last_user_msg = m.content
            break

    replies_data = await loop.run_in_executor(
        None,
        generate_replies_sync,
        last_user_msg or conversation_context,
        conv.participant_username,
        "instagram",
        conversation_context,
    )

    return {"replies": replies_data}


@router.post("/api/inbox/{conversation_id}/archive")
async def archive_inbox_conversation(
    conversation_id: str,
    ctx: TeamContext = Depends(_resolve_team_context),
):
    """Archive a conversation."""
    conv = await get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="conversation_not_found")
    if conv.team_id and conv.team_id != ctx.team_id:
        raise HTTPException(status_code=403, detail="team_mismatch")

    await archive_conversation(conversation_id)
    return {"conversation_id": conversation_id, "status": "archived"}


@router.post("/api/inbox/poll")
async def poll_inbox(ctx: TeamContext = Depends(_resolve_team_context)):
    """Manually poll Instagram DMs for new messages."""
    from bot.services.messages_poller import poll_instagram_conversations
    from bot.services.mentions_store import get_token

    token_row = await get_token("instagram")
    if not token_row or not token_row.access_token:
        raise HTTPException(status_code=400, detail="no_instagram_token")

    convs, msgs = await poll_instagram_conversations(
        token_row.access_token, team_id=ctx.team_id
    )
    return {"conversations_polled": convs, "messages_saved": msgs}


@router.get("/api/inbox/diagnostics")
async def inbox_diagnostics(ctx: TeamContext = Depends(_resolve_team_context)):
    """Check Instagram token and permissions for DM sending."""
    from bot.services.mentions_store import get_token

    result = {
        "token_configured": False,
        "token_valid": False,
        "permissions": [],
        "missing_permissions": [],
        "can_send_dm": False,
        "error": "",
        "page_name": "",
    }

    token_row = await get_token("instagram")
    if not token_row or not token_row.access_token:
        result["error"] = "Instagram токен не настроен. Подключите Instagram в разделе Настройки."
        return result

    result["token_configured"] = True
    token = token_row.access_token

    # Check token validity and permissions via Graph API debug_token
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            # First try /me to check token validity
            me_resp = await client.get(
                "https://graph.instagram.com/v21.0/me",
                params={"access_token": token, "fields": "id,username"},
            )
            if me_resp.status_code == 200:
                me_data = me_resp.json()
                result["token_valid"] = True
                result["page_name"] = me_data.get("username", "")
            else:
                result["error"] = f"Токен недействителен (HTTP {me_resp.status_code}). Переподключите Instagram."
                return result

            # Check permissions via /me/permissions
            perm_resp = await client.get(
                "https://graph.facebook.com/v21.0/me/permissions",
                params={"access_token": token},
            )
            if perm_resp.status_code == 200:
                perm_data = perm_resp.json()
                granted = [
                    p["permission"] for p in perm_data.get("data", [])
                    if p.get("status") == "granted"
                ]
                result["permissions"] = granted

                required = ["instagram_manage_messages", "pages_messaging"]
                missing = [p for p in required if p not in granted]
                result["missing_permissions"] = missing
                result["can_send_dm"] = len(missing) == 0
                if missing:
                    result["error"] = (
                        f"Отсутствуют разрешения: {', '.join(missing)}. "
                        "Переподключите Instagram с нужными правами."
                    )
            else:
                result["error"] = "Не удалось проверить разрешения токена."

    except Exception as exc:
        result["error"] = f"Ошибка проверки: {str(exc)}"

    return result


@router.post("/api/inbox/ingest")
async def ingest_inbox_message(
    payload: InboxIngestPayload,
    _: None = Depends(_require_webhook_auth),
):
    """Webhook endpoint for incoming Instagram DM messages (from Meta webhook)."""
    from bot.services.inbox_store import upsert_conversation

    sent_at = None
    if payload.sent_at:
        try:
            sent_at = datetime.fromisoformat(payload.sent_at.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            pass

    conversation_id, _ = await upsert_conversation(
        platform=payload.platform,
        participant_id=payload.participant_id,
        participant_username=payload.participant_username,
        participant_name=payload.participant_name,
        last_message_preview=payload.content[:200] if payload.content else "",
        last_message_at=sent_at,
    )

    message_id, created = await save_message(
        conversation_id=conversation_id,
        sender_type=payload.sender_type,
        content=payload.content,
        sent_at=sent_at,
        external_id=payload.external_id,
    )

    if created and payload.sender_type == "user":
        asyncio.create_task(_notify_admin_dm(conversation_id, payload))

    return {
        "conversation_id": conversation_id,
        "message_id": message_id,
        "status": "created" if created else "duplicate",
    }


async def _send_instagram_message(recipient_id: str, text: str, team_id: str | None = None) -> None:
    """Send message via Instagram Messaging API (Human Agent tag for >24h window)."""
    from bot.services.mentions_store import get_token

    token_row = await get_token("instagram")
    if not token_row or not token_row.access_token:
        raise ValueError("Instagram token not configured")

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            "https://graph.instagram.com/v21.0/me/messages",
            params={"access_token": token_row.access_token},
            json={
                "recipient": {"id": recipient_id},
                "message": {"text": text},
                "messaging_type": "RESPONSE",
                "tag": "HUMAN_AGENT",
            },
        )
        if r.status_code == 403:
            body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            error_msg = body.get("error", {}).get("message", "")
            raise ValueError(
                f"Instagram API 403: {error_msg or 'нет разрешения instagram_manage_messages или токен истёк'}"
            )
        r.raise_for_status()


async def _notify_admin_dm(conversation_id: str, payload: InboxIngestPayload) -> None:
    """Notify admin about new DM via Telegram."""
    try:
        if not settings.admin_telegram_chat_id:
            return
        preview = payload.content[:80] + ("..." if len(payload.content) > 80 else "")
        miniapp_url = settings.mini_app_url or ""
        text = (
            f"📩 Новое сообщение в DM · Instagram\n"
            f"@{payload.participant_username}: «{preview}»"
        )
        if miniapp_url:
            text += f"\n{miniapp_url}?tab=plans&sub=inbox&conv={conversation_id}"

        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
                json={"chat_id": settings.admin_telegram_chat_id, "text": text},
            )
    except Exception:
        logger.warning("Failed to notify admin about DM %s", conversation_id)


# Need httpx import at module level for _send_instagram_message
import httpx
from config import settings
