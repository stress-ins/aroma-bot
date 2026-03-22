"""Shared helpers for background generation tasks."""
from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable

from bot.services.drafts_store import get_draft, update_draft

# ── In-memory pub/sub for SSE notifications ─────────────────────────────
_generation_events: dict[str, asyncio.Event] = {}


def get_generation_event(draft_id: str) -> asyncio.Event:
    """Return (or create) an asyncio.Event for *draft_id*."""
    if draft_id not in _generation_events:
        _generation_events[draft_id] = asyncio.Event()
    return _generation_events[draft_id]


def cleanup_generation_event(draft_id: str) -> None:
    """Remove the event for *draft_id* when SSE stream ends."""
    _generation_events.pop(draft_id, None)


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
    # Wake up any SSE listeners
    evt = _generation_events.get(draft_id)
    if evt:
        evt.set()


def sse_msg(data: dict) -> str:
    """Format a dict as an SSE data line."""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


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
