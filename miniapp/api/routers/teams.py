"""Team management — CRUD for teams, members, and invites."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from bot.services.team_store import (
    accept_invite,
    add_member,
    create_invite,
    create_team,
    get_member_role,
    get_team,
    get_team_members,
    get_user_teams,
    has_role,
    remove_member,
    update_role,
)
from config import settings
from ..auth import TeamContext, TelegramUser, _resolve_telegram_id, _resolve_telegram_user, _resolve_team_context, require_team_role

router = APIRouter()


class CreateTeamPayload(BaseModel):
    name: str


class InvitePayload(BaseModel):
    role: str = "editor"
    max_uses: int = 1


class UpdateRolePayload(BaseModel):
    role: str


class RenameTeamPayload(BaseModel):
    name: str


# ---------------------------------------------------------------------------
# Teams
# ---------------------------------------------------------------------------


@router.get("/api/teams")
async def list_teams(telegram_id: int = Depends(_resolve_telegram_id)):
    teams = await get_user_teams(telegram_id)
    return {"items": teams}


@router.post("/api/teams")
async def create_team_endpoint(
    body: CreateTeamPayload,
    tg_user: TelegramUser = Depends(_resolve_telegram_user),
):
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="name_required")
    team = await create_team(body.name.strip(), tg_user.telegram_id, creator_username=tg_user.username)
    return {
        "team_id": team.team_id,
        "name": team.name,
        "slug": team.slug,
    }


@router.get("/api/teams/{team_id}")
async def get_team_detail(
    team_id: str,
    telegram_id: int = Depends(_resolve_telegram_id),
):
    role = await get_member_role(team_id, telegram_id)
    if not role:
        raise HTTPException(status_code=403, detail="not_a_team_member")
    team = await get_team(team_id)
    if not team:
        raise HTTPException(status_code=404, detail="team_not_found")
    members = await get_team_members(team_id)
    return {
        "team_id": team.team_id,
        "name": team.name,
        "slug": team.slug,
        "created_by": team.created_by,
        "role": role,
        "members": members,
    }


@router.patch("/api/teams/{team_id}")
async def rename_team(
    team_id: str,
    body: RenameTeamPayload,
    ctx: TeamContext = Depends(require_team_role("owner")),
):
    if ctx.team_id != team_id:
        raise HTTPException(status_code=403, detail="team_mismatch")
    from sqlalchemy import update as sa_update
    from db.models import TeamModel
    from db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        await session.execute(
            sa_update(TeamModel)
            .where(TeamModel.team_id == team_id)
            .values(name=body.name.strip())
        )
        await session.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Members
# ---------------------------------------------------------------------------


@router.get("/api/teams/{team_id}/members")
async def list_members(
    team_id: str,
    telegram_id: int = Depends(_resolve_telegram_id),
):
    role = await get_member_role(team_id, telegram_id)
    if not role:
        raise HTTPException(status_code=403, detail="not_a_team_member")
    members = await get_team_members(team_id)
    return {"items": members}


@router.patch("/api/teams/{team_id}/members/{member_id}/role")
async def update_member_role(
    team_id: str,
    member_id: int,
    body: UpdateRolePayload,
    ctx: TeamContext = Depends(require_team_role("owner")),
):
    if ctx.team_id != team_id:
        raise HTTPException(status_code=403, detail="team_mismatch")
    ok = await update_role(team_id, member_id, body.role)
    if not ok:
        raise HTTPException(status_code=404, detail="member_not_found")
    return {"ok": True}


@router.delete("/api/teams/{team_id}/members/{member_id}")
async def remove_team_member(
    team_id: str,
    member_id: int,
    ctx: TeamContext = Depends(require_team_role("owner")),
):
    if ctx.team_id != team_id:
        raise HTTPException(status_code=403, detail="team_mismatch")
    if member_id == ctx.telegram_id:
        raise HTTPException(status_code=400, detail="cannot_remove_self")
    ok = await remove_member(team_id, member_id)
    if not ok:
        raise HTTPException(status_code=404, detail="member_not_found")
    return {"ok": True}


@router.post("/api/teams/{team_id}/leave")
async def leave_team(
    team_id: str,
    telegram_id: int = Depends(_resolve_telegram_id),
):
    role = await get_member_role(team_id, telegram_id)
    if not role:
        raise HTTPException(status_code=403, detail="not_a_team_member")
    if role == "owner":
        raise HTTPException(status_code=400, detail="owner_cannot_leave")
    await remove_member(team_id, telegram_id)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Invites
# ---------------------------------------------------------------------------


@router.post("/api/teams/{team_id}/invites")
async def create_team_invite(
    team_id: str,
    body: InvitePayload,
    ctx: TeamContext = Depends(require_team_role("owner")),
):
    if ctx.team_id != team_id:
        raise HTTPException(status_code=403, detail="team_mismatch")
    invite = await create_invite(
        team_id=team_id,
        created_by=ctx.telegram_id,
        role=body.role,
        max_uses=body.max_uses,
    )
    return {
        "invite_code": invite.invite_code,
        "deep_link": f"https://t.me/{settings.telegram_bot_username}?start=invite_{invite.invite_code}",
    }


@router.post("/api/invites/{invite_code}/accept")
async def accept_team_invite(
    invite_code: str,
    tg_user: TelegramUser = Depends(_resolve_telegram_user),
):
    result = await accept_invite(invite_code, tg_user.telegram_id, username=tg_user.username)
    if result is None:
        raise HTTPException(status_code=404, detail="invite_not_found_or_expired")
    return result
