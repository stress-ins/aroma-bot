from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException

from bot.services.drafts_store import DraftRecord, get_draft
from .auth import TeamContext, _require_auth, _resolve_team_context


def require_draft(kind: str) -> Callable:
    """FastAPI dependency factory: fetch draft by ID, validate kind AND team membership."""
    async def _dep(draft_id: str, ctx: TeamContext = Depends(_resolve_team_context)) -> DraftRecord:
        draft = await get_draft(draft_id)
        if not draft or draft.kind != kind:
            raise HTTPException(status_code=404, detail=f"{kind}_not_found")
        if draft.team_id and draft.team_id != ctx.team_id:
            raise HTTPException(status_code=403, detail="team_mismatch")
        return draft
    return _dep


def require_draft_any_kind() -> Callable:
    """Fetch draft by ID (any kind), validate team membership."""
    async def _dep(draft_id: str, ctx: TeamContext = Depends(_resolve_team_context)) -> DraftRecord:
        draft = await get_draft(draft_id)
        if not draft:
            raise HTTPException(status_code=404, detail="draft_not_found")
        if draft.team_id and draft.team_id != ctx.team_id:
            raise HTTPException(status_code=403, detail="team_mismatch")
        return draft
    return _dep


def verify_team_draft(draft: DraftRecord, ctx: TeamContext) -> None:
    """Raise 403 if draft doesn't belong to the user's team."""
    if draft.team_id and draft.team_id != ctx.team_id:
        raise HTTPException(status_code=403, detail="team_mismatch")
