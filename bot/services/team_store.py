from __future__ import annotations

import logging
import secrets
import re
from datetime import datetime, timezone

from sqlalchemy import select, update, delete

from db.session import AsyncSessionLocal
from db.models import TeamModel, TeamMemberModel, TeamInviteModel

logger = logging.getLogger(__name__)

DEFAULT_TEAM_ID = "00000000-0000-0000-0000-000000000001"
VALID_ROLES = ("owner", "editor", "viewer")
ROLE_RANK = {"owner": 3, "editor": 2, "viewer": 1}


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9а-яё]+", "-", name.lower().strip())
    return slug.strip("-")[:60] or "team"


async def create_team(name: str, creator_telegram_id: int, creator_username: str = "") -> TeamModel:
    async with AsyncSessionLocal() as session:
        slug_base = _slugify(name)
        slug = slug_base
        # Ensure unique slug
        for i in range(1, 100):
            exists = (await session.execute(
                select(TeamModel).where(TeamModel.slug == slug)
            )).scalar_one_or_none()
            if not exists:
                break
            slug = f"{slug_base}-{i}"

        team = TeamModel(name=name, slug=slug, created_by=creator_telegram_id)
        session.add(team)
        await session.flush()

        member = TeamMemberModel(
            team_id=team.team_id,
            telegram_id=creator_telegram_id,
            username=creator_username,
            role="owner",
        )
        session.add(member)
        await session.commit()
        await session.refresh(team)
        return team


async def get_user_teams(telegram_id: int) -> list[dict]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(TeamModel, TeamMemberModel.role)
            .join(TeamMemberModel, TeamModel.team_id == TeamMemberModel.team_id)
            .where(TeamMemberModel.telegram_id == telegram_id)
            .order_by(TeamModel.created_at)
        )
        return [
            {
                "team_id": team.team_id,
                "name": team.name,
                "slug": team.slug,
                "role": role,
                "created_by": team.created_by,
            }
            for team, role in result.all()
        ]


async def get_default_team(telegram_id: int) -> TeamModel:
    teams = await get_user_teams(telegram_id)
    if teams:
        return await get_team(teams[0]["team_id"])

    # Auto-create personal workspace
    return await create_team("Personal", telegram_id)


async def get_team(team_id: str) -> TeamModel | None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(TeamModel).where(TeamModel.team_id == team_id)
        )
        return result.scalar_one_or_none()


async def get_team_members(team_id: str) -> list[dict]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(TeamMemberModel)
            .where(TeamMemberModel.team_id == team_id)
            .order_by(TeamMemberModel.joined_at)
        )
        return [
            {
                "telegram_id": m.telegram_id,
                "username": m.username or "",
                "role": m.role,
                "joined_at": m.joined_at.isoformat() if m.joined_at else None,
            }
            for m in result.scalars().all()
        ]


async def get_member_role(team_id: str, telegram_id: int) -> str | None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(TeamMemberModel.role)
            .where(
                TeamMemberModel.team_id == team_id,
                TeamMemberModel.telegram_id == telegram_id,
            )
        )
        row = result.scalar_one_or_none()
        return row


async def add_member(team_id: str, telegram_id: int, role: str = "viewer", username: str = "") -> TeamMemberModel:
    if role not in VALID_ROLES:
        raise ValueError(f"Invalid role: {role}")
    async with AsyncSessionLocal() as session:
        member = TeamMemberModel(team_id=team_id, telegram_id=telegram_id, username=username, role=role)
        session.add(member)
        await session.commit()
        await session.refresh(member)
        return member


async def remove_member(team_id: str, telegram_id: int) -> bool:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            delete(TeamMemberModel).where(
                TeamMemberModel.team_id == team_id,
                TeamMemberModel.telegram_id == telegram_id,
            )
        )
        await session.commit()
        return result.rowcount > 0


async def update_role(team_id: str, telegram_id: int, new_role: str) -> bool:
    if new_role not in VALID_ROLES:
        raise ValueError(f"Invalid role: {new_role}")
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            update(TeamMemberModel)
            .where(
                TeamMemberModel.team_id == team_id,
                TeamMemberModel.telegram_id == telegram_id,
            )
            .values(role=new_role)
        )
        await session.commit()
        return result.rowcount > 0


async def create_invite(
    team_id: str,
    created_by: int,
    role: str = "editor",
    max_uses: int = 1,
    expires_at: datetime | None = None,
) -> TeamInviteModel:
    if role not in VALID_ROLES or role == "owner":
        raise ValueError(f"Cannot create invite with role: {role}")
    async with AsyncSessionLocal() as session:
        invite = TeamInviteModel(
            invite_code=secrets.token_urlsafe(16),
            team_id=team_id,
            created_by=created_by,
            role=role,
            max_uses=max_uses,
            expires_at=expires_at,
        )
        session.add(invite)
        await session.commit()
        await session.refresh(invite)
        return invite


async def accept_invite(invite_code: str, telegram_id: int, username: str = "") -> dict | None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(TeamInviteModel).where(TeamInviteModel.invite_code == invite_code)
        )
        invite = result.scalar_one_or_none()
        if not invite:
            return None

        # Check expiry
        if invite.expires_at and datetime.now(timezone.utc) > invite.expires_at:
            return None

        # Check usage limit
        if invite.uses_count >= invite.max_uses:
            return None

        # Check if already a member
        existing = await session.execute(
            select(TeamMemberModel).where(
                TeamMemberModel.team_id == invite.team_id,
                TeamMemberModel.telegram_id == telegram_id,
            )
        )
        if existing.scalar_one_or_none():
            return {"already_member": True, "team_id": invite.team_id}

        # Add member
        member = TeamMemberModel(
            team_id=invite.team_id,
            telegram_id=telegram_id,
            username=username,
            role=invite.role,
        )
        session.add(member)
        invite.uses_count += 1
        await session.commit()

        team = await session.execute(
            select(TeamModel).where(TeamModel.team_id == invite.team_id)
        )
        team_obj = team.scalar_one_or_none()
        return {
            "joined": True,
            "team_id": invite.team_id,
            "team_name": team_obj.name if team_obj else "",
            "role": invite.role,
        }


def has_role(user_role: str | None, min_role: str) -> bool:
    if not user_role:
        return False
    return ROLE_RANK.get(user_role, 0) >= ROLE_RANK.get(min_role, 0)
