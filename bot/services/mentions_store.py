from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import or_, select

from db.session import AsyncSessionLocal
from db.models import MentionModel, MentionReplyModel, PlatformTokenModel

logger = logging.getLogger(__name__)


async def find_mention_by_external_id(platform: str, external_id: str) -> MentionModel | None:
    """Find an existing mention by platform + external_id (for deduplication)."""
    if not external_id:
        return None
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(MentionModel).filter(
                MentionModel.platform == platform,
                MentionModel.external_id == external_id,
            )
        )
        return result.scalar_one_or_none()


async def save_mention(
    platform: str,
    external_id: str,
    type: str,
    author_username: str,
    author_name: str,
    content: str,
    url: str = "",
    context_post: str = "",
    team_id: str | None = None,
) -> tuple[str, bool]:
    """Save a new mention and return (mention_id, created).

    If a mention with the same platform + external_id already exists,
    returns the existing mention_id and created=False (deduplication).
    """
    # Deduplicate by platform + external_id
    existing = await find_mention_by_external_id(platform, external_id)
    if existing is not None:
        return existing.mention_id, False

    mention_id = str(uuid4())
    async with AsyncSessionLocal() as session:
        model = MentionModel(
            mention_id=mention_id,
            platform=platform,
            external_id=external_id,
            type=type,
            author_username=author_username,
            author_name=author_name,
            content=content,
            url=url,
            context_post=context_post,
            received_at=datetime.now(timezone.utc),
            status="pending",
        )
        if team_id is not None:
            model.team_id = team_id
        session.add(model)
        await session.commit()
    return mention_id, True


async def get_mention(mention_id: str) -> MentionModel | None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(MentionModel).filter(MentionModel.mention_id == mention_id)
        )
        return result.scalar_one_or_none()


async def list_mentions(
    platform: str | None = None,
    status: str | None = None,
    limit: int = 20,
    offset: int = 0,
    team_id: str | None = None,
) -> list[MentionModel]:
    async with AsyncSessionLocal() as session:
        query = select(MentionModel).order_by(MentionModel.received_at.desc())
        if team_id is not None:
            query = query.filter(or_(MentionModel.team_id == team_id, MentionModel.team_id.is_(None)))
        if platform and platform != "all":
            query = query.filter(MentionModel.platform == platform)
        if status and status != "all":
            query = query.filter(MentionModel.status == status)
        query = query.limit(limit).offset(offset)
        result = await session.execute(query)
        return list(result.scalars().all())


async def save_replies(mention_id: str, replies: list[dict]) -> list[MentionReplyModel]:
    """Save generated reply variants for a mention."""
    saved: list[MentionReplyModel] = []
    async with AsyncSessionLocal() as session:
        for r in replies:
            model = MentionReplyModel(
                reply_id=str(uuid4()),
                mention_id=mention_id,
                tone=r.get("tone", "warm"),
                content=r.get("content", ""),
                generated_at=datetime.now(timezone.utc),
                selected=False,
            )
            session.add(model)
            saved.append(model)
        await session.commit()
    return saved


async def list_replies(mention_id: str) -> list[MentionReplyModel]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(MentionReplyModel)
            .filter(MentionReplyModel.mention_id == mention_id)
            .order_by(MentionReplyModel.generated_at.asc())
        )
        return list(result.scalars().all())


async def select_reply(reply_id: str) -> MentionReplyModel | None:
    """Mark a reply as selected (deselect all others in the same mention)."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(MentionReplyModel).filter(MentionReplyModel.reply_id == reply_id)
        )
        reply = result.scalar_one_or_none()
        if not reply:
            return None
        # Deselect siblings
        siblings_result = await session.execute(
            select(MentionReplyModel).filter(MentionReplyModel.mention_id == reply.mention_id)
        )
        for sibling in siblings_result.scalars().all():
            sibling.selected = sibling.reply_id == reply_id
        await session.commit()
        await session.refresh(reply)
        return reply


async def mark_replied(mention_id: str, published_at: datetime | None = None) -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(MentionModel).filter(MentionModel.mention_id == mention_id)
        )
        mention = result.scalar_one_or_none()
        if mention:
            mention.status = "replied"
            await session.commit()


async def mark_reply_published(reply_id: str, error: str = "") -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(MentionReplyModel).filter(MentionReplyModel.reply_id == reply_id)
        )
        reply = result.scalar_one_or_none()
        if reply:
            reply.published_at = datetime.now(timezone.utc)
            reply.publish_error = error
            await session.commit()


async def ignore_mention(mention_id: str) -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(MentionModel).filter(MentionModel.mention_id == mention_id)
        )
        mention = result.scalar_one_or_none()
        if mention:
            mention.status = "ignored"
            await session.commit()


async def get_token(platform: str) -> PlatformTokenModel | None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(PlatformTokenModel).filter(PlatformTokenModel.platform == platform)
        )
        return result.scalar_one_or_none()


async def get_token_for_team(platform: str, team_id: str) -> PlatformTokenModel | None:
    """Get OAuth token for a specific team + platform."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(PlatformTokenModel).filter(
                PlatformTokenModel.platform == platform,
                PlatformTokenModel.team_id == team_id,
            )
        )
        token = result.scalar_one_or_none()
        if token is not None:
            return token
        # Fallback to global (team_id=None) token
        result = await session.execute(
            select(PlatformTokenModel).filter(
                PlatformTokenModel.platform == platform,
                PlatformTokenModel.team_id.is_(None),
            )
        )
        return result.scalar_one_or_none()


async def upsert_token(
    platform: str,
    access_token: str,
    expires_at: datetime | None = None,
    refresh_token: str = "",
) -> PlatformTokenModel:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(PlatformTokenModel).filter(PlatformTokenModel.platform == platform)
        )
        model = result.scalar_one_or_none()
        if model:
            model.access_token = access_token
            model.expires_at = expires_at
            if refresh_token:
                model.refresh_token = refresh_token
            model.updated_at = datetime.now(timezone.utc)
        else:
            model = PlatformTokenModel(
                platform=platform,
                access_token=access_token,
                refresh_token=refresh_token,
                expires_at=expires_at,
                updated_at=datetime.now(timezone.utc),
            )
            session.add(model)
        await session.commit()
        await session.refresh(model)
        return model


async def list_tokens(*, team_id: str | None = None) -> list[PlatformTokenModel]:
    async with AsyncSessionLocal() as session:
        query = select(PlatformTokenModel)
        if team_id is not None:
            query = query.filter(or_(PlatformTokenModel.team_id == team_id, PlatformTokenModel.team_id.is_(None)))
        result = await session.execute(query)
        return list(result.scalars().all())


async def list_expiring_tokens(days: int = 7) -> list[PlatformTokenModel]:
    from datetime import timedelta
    threshold = datetime.now(timezone.utc) + timedelta(days=days)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(PlatformTokenModel).filter(
                PlatformTokenModel.expires_at.isnot(None),
                PlatformTokenModel.expires_at <= threshold,
            )
        )
        return list(result.scalars().all())
