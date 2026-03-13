from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException

from bot.services.drafts_store import DraftRecord, get_draft
from .auth import _require_auth


def require_draft(kind: str) -> Callable:
    """FastAPI dependency factory: fetch draft by ID and validate its kind."""
    async def _dep(draft_id: str, _: None = Depends(_require_auth)) -> DraftRecord:
        draft = await get_draft(draft_id)
        if not draft or draft.kind != kind:
            raise HTTPException(status_code=404, detail=f"{kind}_not_found")
        return draft
    return _dep
