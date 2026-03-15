"""Content approval state machine.

Allowed transitions::

    draft → pending_review → approved → scheduled → published
                           ↘ revision_requested → draft
    scheduled / published → failed
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from bot.services.drafts_store import get_draft, update_draft, DraftRecord

logger = logging.getLogger(__name__)

VALID_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"pending_review"},
    "pending_review": {"approved", "revision_requested"},
    "revision_requested": {"draft"},
    "approved": {"scheduled"},
    "scheduled": {"published", "failed"},
    "published": {"failed"},
}


class InvalidTransitionError(ValueError):
    """Raised when a status transition is not allowed."""

    def __init__(self, current: str, target: str) -> None:
        super().__init__(f"Cannot transition from '{current}' to '{target}'")
        self.current = current
        self.target = target


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


async def _transition(draft_id: str, target: str, **kwargs) -> DraftRecord:
    draft = await get_draft(draft_id)
    if draft is None:
        raise ValueError(f"Draft not found: {draft_id}")
    allowed = VALID_TRANSITIONS.get(draft.status, set())
    if target not in allowed:
        raise InvalidTransitionError(draft.status, target)
    result = await update_draft(draft_id, status=target, **kwargs)
    if result is None:  # pragma: no cover
        raise ValueError(f"Failed to update draft: {draft_id}")
    logger.info("Draft %s: %s → %s", draft_id, draft.status, target)
    return result


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------


async def submit_for_review(draft_id: str) -> DraftRecord:
    """draft → pending_review"""
    return await _transition(draft_id, "pending_review")


async def approve(draft_id: str) -> DraftRecord:
    """pending_review → approved"""
    return await _transition(draft_id, "approved")


async def request_revision(draft_id: str, instructions: str) -> DraftRecord:
    """pending_review → revision_requested (stores revision_notes)"""
    return await _transition(
        draft_id, "revision_requested", revision_notes=instructions
    )


async def schedule(
    draft_id: str, dt: datetime, platforms: list[str]
) -> DraftRecord:
    """approved → scheduled"""
    return await _transition(
        draft_id,
        "scheduled",
        scheduled_at=dt,
        publish_platforms=platforms,
    )


async def mark_published(
    draft_id: str, platform_post_ids: dict
) -> DraftRecord:
    """scheduled → published"""
    return await _transition(
        draft_id,
        "published",
        published_at=datetime.now(timezone.utc),
        external_ids=platform_post_ids,
    )


async def mark_failed(draft_id: str, error: str) -> DraftRecord:
    """scheduled | published → failed"""
    return await _transition(draft_id, "failed", error=error)
