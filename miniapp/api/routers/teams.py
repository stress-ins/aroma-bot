"""Team management — CRUD for teams, members, and invites."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from bot.services.mentions_store import get_token, list_tokens
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
from bot.services.brand_settings_store import get_brand_settings, update_brand_settings
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
    name: str | None = None
    default_domain: str | None = None


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
    team = await create_team(body.name.strip(), tg_user.telegram_id, creator_username=tg_user.username, creator_first_name=tg_user.first_name)
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

    # Connected social accounts for this team
    tokens = await list_tokens(team_id=team_id)
    token_map: dict[str, dict] = {}
    for t in tokens:
        if t.platform in ("threads", "instagram"):
            token_map[t.platform] = {
                "connected": bool(t.access_token),
                "expires_at": t.expires_at.isoformat() if t.expires_at else None,
            }
    connected_accounts = []
    for platform in ("threads", "instagram"):
        info = token_map.get(platform, {})
        acc: dict = {
            "platform": platform,
            "connected": info.get("connected", False),
            "username": None,
            "expires_at": info.get("expires_at"),
        }
        username_token = await get_token(f"{platform}_username")
        if username_token and username_token.access_token:
            acc["username"] = username_token.access_token
        connected_accounts.append(acc)

    # Check if team avatar exists
    from pathlib import Path
    avatar_dir = Path(__file__).parent.parent.parent.parent / "data" / "avatars"
    avatar_file = avatar_dir / f"team_{team_id}.jpg"
    has_avatar = avatar_file.exists()

    # Default domain preference
    bs = await get_brand_settings(team_id)
    default_domain = getattr(bs, "default_domain", "aroma") or "aroma"

    return {
        "team_id": team.team_id,
        "name": team.name,
        "slug": team.slug,
        "created_by": team.created_by,
        "role": role,
        "members": members,
        "connected_accounts": connected_accounts,
        "has_avatar": has_avatar,
        "avatar_url": f"/api/teams/{team_id}/avatar" if has_avatar else None,
        "default_domain": default_domain,
    }


@router.patch("/api/teams/{team_id}")
async def rename_team(
    team_id: str,
    body: RenameTeamPayload,
    ctx: TeamContext = Depends(require_team_role("owner")),
):
    if ctx.team_id != team_id:
        raise HTTPException(status_code=403, detail="team_mismatch")

    # Update team name if provided
    if body.name is not None:
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

    # Update default_domain if provided
    if body.default_domain is not None:
        valid_domains = ("aroma", "body", "sound")
        if body.default_domain not in valid_domains:
            raise HTTPException(status_code=400, detail="invalid_domain")
        await update_brand_settings(team_id, default_domain=body.default_domain)

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
# Avatar
# ---------------------------------------------------------------------------


@router.post("/api/teams/{team_id}/avatar")
async def upload_team_avatar(
    team_id: str,
    file: UploadFile = File(...),
    ctx: TeamContext = Depends(require_team_role("owner")),
):
    """Upload team avatar image (JPG/PNG, max 2MB)."""
    if ctx.team_id != team_id:
        raise HTTPException(status_code=403, detail="team_mismatch")

    content_type = file.content_type or ""
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="image_required")

    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="file_too_large")

    from pathlib import Path
    from PIL import Image
    import io

    img = Image.open(io.BytesIO(data)).convert("RGB")
    # Center-crop to square first, then resize to 512x512
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    img = img.crop((left, top, left + side, top + side))
    img = img.resize((512, 512), Image.LANCZOS)

    avatar_dir = Path(__file__).parent.parent.parent.parent / "data" / "avatars"
    avatar_dir.mkdir(parents=True, exist_ok=True)
    avatar_path = avatar_dir / f"team_{team_id}.jpg"
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    avatar_path.write_bytes(buf.getvalue())

    return {"ok": True, "avatar_url": f"/api/teams/{team_id}/avatar"}


@router.get("/api/teams/{team_id}/avatar")
async def get_team_avatar(team_id: str):
    """Serve team avatar image."""
    from pathlib import Path
    from fastapi.responses import FileResponse

    avatar_dir = Path(__file__).parent.parent.parent.parent / "data" / "avatars"
    avatar_path = avatar_dir / f"team_{team_id}.jpg"
    if not avatar_path.exists():
        raise HTTPException(status_code=404, detail="avatar_not_found")
    return FileResponse(
        avatar_path,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-cache, must-revalidate"},
    )


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
    result = await accept_invite(invite_code, tg_user.telegram_id, username=tg_user.username, first_name=tg_user.first_name)
    if result is None:
        raise HTTPException(status_code=404, detail="invite_not_found_or_expired")
    return result
