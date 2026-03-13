"""Reusable FastAPI dependencies."""
from __future__ import annotations

from fastapi import Depends, HTTPException

from bot.services.drafts_store import DraftModel, get_draft
from .auth import _require_auth


def require_draft(kind: str | None = None):
    """Return a dependency that fetches a draft and checks its kind.

    If *kind* is given the draft must have that kind; otherwise any draft
    is accepted.  Raises 404 when the draft is missing or the kind mismatches.
    """
    detail = f"{kind}_not_found" if kind else "draft_not_found"

    async def _dep(draft_id: str, _: None = Depends(_require_auth)) -> DraftModel:
        draft = await get_draft(draft_id)
        if not draft or (kind is not None and draft.kind != kind):
            raise HTTPException(status_code=404, detail=detail)
        return draft

    return _dep
