"""Inbox store — CRUD for Instagram DM conversations and messages."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import desc, or_, select, update

from db.models import ConversationModel, DirectMessageModel
from db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)


async def list_conversations(
    team_id: str | None = None,
    status: str = "active",
    limit: int = 20,
    offset: int = 0,
) -> list[ConversationModel]:
    """List conversations ordered by last_message_at desc."""
    async with AsyncSessionLocal() as session:
        q = select(ConversationModel).order_by(desc(ConversationModel.last_message_at))
        if team_id:
            q = q.filter(or_(ConversationModel.team_id == team_id, ConversationModel.team_id.is_(None)))
        if status and status != "all":
            q = q.filter(ConversationModel.status == status)
        q = q.limit(limit).offset(offset)
        result = await session.execute(q)
        return list(result.scalars().all())


async def get_conversation(conversation_id: str) -> ConversationModel | None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ConversationModel).filter(
                ConversationModel.conversation_id == conversation_id
            )
        )
        return result.scalar_one_or_none()


async def find_conversation_by_participant(
    platform: str, participant_id: str, team_id: str | None = None
) -> ConversationModel | None:
    async with AsyncSessionLocal() as session:
        q = select(ConversationModel).filter(
            ConversationModel.platform == platform,
            ConversationModel.participant_id == participant_id,
        )
        if team_id:
            q = q.filter(or_(ConversationModel.team_id == team_id, ConversationModel.team_id.is_(None)))
        result = await session.execute(q)
        return result.scalar_one_or_none()


async def upsert_conversation(
    *,
    platform: str = "instagram",
    participant_id: str,
    participant_username: str = "",
    participant_name: str = "",
    last_message_preview: str = "",
    last_message_at: datetime | None = None,
    team_id: str | None = None,
) -> tuple[str, bool]:
    """Create or update a conversation. Returns (conversation_id, created)."""
    existing = await find_conversation_by_participant(platform, participant_id, team_id)
    if existing:
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(ConversationModel)
                .where(ConversationModel.conversation_id == existing.conversation_id)
                .values(
                    participant_username=participant_username or existing.participant_username,
                    participant_name=participant_name or existing.participant_name,
                    last_message_preview=last_message_preview or existing.last_message_preview,
                    last_message_at=last_message_at or existing.last_message_at,
                    unread_count=ConversationModel.unread_count + 1,
                )
            )
            await session.commit()
        return existing.conversation_id, False

    cid = str(uuid4())
    async with AsyncSessionLocal() as session:
        conv = ConversationModel(
            conversation_id=cid,
            team_id=team_id,
            platform=platform,
            participant_id=participant_id,
            participant_username=participant_username,
            participant_name=participant_name,
            last_message_preview=last_message_preview,
            last_message_at=last_message_at or datetime.now(timezone.utc),
            status="active",
            unread_count=1,
        )
        session.add(conv)
        await session.commit()
    return cid, True


async def archive_conversation(conversation_id: str) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(ConversationModel)
            .where(ConversationModel.conversation_id == conversation_id)
            .values(status="archived")
        )
        await session.commit()


async def mark_conversation_read(conversation_id: str) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(ConversationModel)
            .where(ConversationModel.conversation_id == conversation_id)
            .values(unread_count=0)
        )
        await session.commit()


async def list_messages(conversation_id: str, limit: int = 50) -> list[DirectMessageModel]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(DirectMessageModel)
            .filter(DirectMessageModel.conversation_id == conversation_id)
            .order_by(DirectMessageModel.sent_at)
            .limit(limit)
        )
        return list(result.scalars().all())


async def find_message_by_external_id(external_id: str) -> DirectMessageModel | None:
    if not external_id:
        return None
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(DirectMessageModel).filter(
                DirectMessageModel.external_id == external_id
            )
        )
        return result.scalar_one_or_none()


async def save_message(
    *,
    conversation_id: str,
    sender_type: str = "user",
    content: str = "",
    sent_at: datetime | None = None,
    external_id: str = "",
) -> tuple[str, bool]:
    """Save a message. Deduplicates by external_id. Returns (message_id, created)."""
    if external_id:
        existing = await find_message_by_external_id(external_id)
        if existing:
            return existing.message_id, False

    mid = str(uuid4())
    ts = sent_at or datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        msg = DirectMessageModel(
            message_id=mid,
            conversation_id=conversation_id,
            sender_type=sender_type,
            content=content,
            sent_at=ts,
            external_id=external_id,
        )
        session.add(msg)
        await session.commit()

    # Update conversation preview
    preview = content[:200] if content else ""
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(ConversationModel)
            .where(ConversationModel.conversation_id == conversation_id)
            .values(
                last_message_preview=preview,
                last_message_at=ts,
            )
        )
        await session.commit()

    return mid, True
