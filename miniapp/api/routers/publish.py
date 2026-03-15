"""Publish API — publish/schedule drafts, check status, cancel scheduled posts."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from bot.services.drafts_store import get_draft, list_scheduled_drafts_due, update_draft
from bot.services.publish_log_store import list_all_logs, list_logs
from bot.services.publisher import cancel_scheduled, check_status, publish
from ..auth import _require_auth

router = APIRouter()


class PublishPayload(BaseModel):
    platforms: list[str] = Field(default_factory=list)
    scheduled_at: str | None = Field(default=None)


@router.post("/api/drafts/{draft_id}/publish")
async def publish_draft(draft_id: str, payload: PublishPayload, _: None = Depends(_require_auth)):
    draft = await get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="draft_not_found")
    if draft.status != "approved":
        raise HTTPException(status_code=400, detail="draft_must_be_approved")
    if not payload.platforms:
        raise HTTPException(status_code=400, detail="platforms_required")

    valid_platforms = {"threads", "instagram", "telegram"}
    for p in payload.platforms:
        if p not in valid_platforms:
            raise HTTPException(status_code=400, detail=f"invalid_platform: {p}")

    scheduled_at: datetime | None = None
    if payload.scheduled_at:
        try:
            scheduled_at = datetime.fromisoformat(payload.scheduled_at)
            if scheduled_at.tzinfo is None:
                scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)
        except ValueError:
            raise HTTPException(status_code=400, detail="invalid_scheduled_at_format")

    results = await publish(draft_id, payload.platforms, scheduled_at=scheduled_at)
    return {"draft_id": draft_id, "results": results}


@router.get("/api/drafts/{draft_id}/publish-status")
async def publish_status(draft_id: str, _: None = Depends(_require_auth)):
    draft = await get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="draft_not_found")

    logs = await list_logs(draft_id)
    remote_status = await check_status(draft_id)
    return {"logs": logs, "remote_status": remote_status}


@router.delete("/api/drafts/{draft_id}/publish-schedule")
async def cancel_publish_schedule(draft_id: str, _: None = Depends(_require_auth)):
    draft = await get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="draft_not_found")
    if draft.status != "scheduled":
        raise HTTPException(status_code=400, detail="draft_not_scheduled")

    results = await cancel_scheduled(draft_id)
    return {"draft_id": draft_id, "results": results}


@router.post("/api/publish/{item_id}")
async def publish_by_id(item_id: str, _: None = Depends(_require_auth)):
    """Immediate publish endpoint (used by scheduler internally)."""
    draft = await get_draft(item_id)
    if not draft:
        raise HTTPException(status_code=404, detail="draft_not_found")
    if draft.status not in ("scheduled", "approved"):
        raise HTTPException(status_code=400, detail="draft_not_ready")
    platforms = draft.publish_platforms or ["threads"]
    results = await publish(item_id, platforms)
    return {"draft_id": item_id, "results": results}


@router.get("/api/publish/scheduled")
async def scheduled_posts(_: None = Depends(_require_auth)):
    from bot.services.drafts_store import list_recent_drafts
    records = await list_recent_drafts(limit=200, newest_first=True)
    scheduled = [
        {
            "draft_id": r.draft_id,
            "kind": r.kind,
            "topic": r.topic,
            "scheduled_at": r.scheduled_at,
            "publish_platforms": r.publish_platforms,
            "status": r.status,
        }
        for r in records
        if r.scheduled_at and r.status in ("approved", "scheduled")
    ]
    return {"items": scheduled}


@router.get("/api/publish/history")
async def publish_history(limit: int = 50, _: None = Depends(_require_auth)):
    logs = await list_all_logs(limit=limit)
    return {"items": logs}
