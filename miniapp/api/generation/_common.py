"""Shared helpers for background generation tasks."""
from __future__ import annotations

from collections.abc import Awaitable

from bot.services.drafts_store import get_draft, update_draft


async def set_generation_state(
    draft_id: str,
    *,
    pending: bool,
    stage: str = "",
    message: str = "",
    error: str = "",
) -> None:
    draft = await get_draft(draft_id)
    if not draft:
        return
    payload = dict(draft.payload or {})
    payload["generation_pending"] = pending
    payload["generation_stage"] = stage
    payload["generation_message"] = message
    if error:
        payload["generation_error"] = error
    else:
        payload.pop("generation_error", None)
    await update_draft(draft_id, payload=payload, status="draft")


async def _run_generation_task(
    draft_id: str,
    coro: Awaitable[None],
    error_message: str,
) -> None:
    try:
        await coro
        await set_generation_state(draft_id, pending=False)
    except Exception as exc:
        await set_generation_state(
            draft_id,
            pending=False,
            stage="error",
            message=error_message,
            error=str(exc),
        )
