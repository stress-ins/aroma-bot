"""Publish API — publish/schedule drafts, check status, cancel scheduled posts."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from bot.services.drafts_store import get_draft, list_scheduled_drafts_due, update_draft
from bot.services.publish_log_store import list_all_logs, list_logs
from bot.services.publisher import cancel_scheduled, check_status, publish
from ..auth import TeamContext, _require_auth, _resolve_init_data, _resolve_sse_auth, _resolve_team_context, require_tier
from ..models import ScheduleSeriesRequest

logger = logging.getLogger(__name__)

router = APIRouter()


class PublishPayload(BaseModel):
    platforms: list[str] = Field(default_factory=list)
    scheduled_at: str | None = Field(default=None)


@router.post("/api/drafts/{draft_id}/publish", dependencies=[Depends(require_tier("expert"))])
async def publish_draft(draft_id: str, payload: PublishPayload, _: None = Depends(_require_auth)):
    draft = await get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="draft_not_found")
    if draft.status != "approved":
        raise HTTPException(status_code=400, detail="draft_must_be_approved")
    if not payload.platforms:
        raise HTTPException(status_code=400, detail="platforms_required")

    valid_platforms = {"threads", "instagram", "telegram", "tiktok"}
    for p in payload.platforms:
        if p not in valid_platforms:
            raise HTTPException(status_code=400, detail=f"invalid_platform: {p}")

    # TikTok requires video content
    if "tiktok" in payload.platforms:
        draft_payload = draft.payload or {}
        video_info = draft_payload.get("video") or {}
        has_video = bool(
            (isinstance(video_info, dict) and (video_info.get("public_url") or video_info.get("url")))
            or draft_payload.get("video_url")
        )
        if not has_video:
            raise HTTPException(status_code=400, detail="tiktok_requires_video")

    scheduled_at: datetime | None = None
    if payload.scheduled_at:
        try:
            scheduled_at = datetime.fromisoformat(payload.scheduled_at)
            if scheduled_at.tzinfo is None:
                scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)
        except ValueError:
            raise HTTPException(status_code=400, detail="invalid_scheduled_at_format")

    if scheduled_at and scheduled_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="scheduled_at_must_be_in_future")

    try:
        results = await publish(draft_id, payload.platforms, scheduled_at=scheduled_at)
    except Exception as exc:
        logger.exception("publish failed for draft %s", draft_id)
        from bot.handlers.monitor import notify_owner
        notify_owner(f"⚠️ Publish failed for draft {draft_id}:\n{exc}")
        raise HTTPException(status_code=500, detail="publish_failed")
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


@router.get("/api/publish/scheduled")
async def scheduled_posts(ctx: TeamContext = Depends(_resolve_team_context)):
    from bot.services.drafts_store import list_recent_drafts
    records = await list_recent_drafts(limit=200, newest_first=True, team_id=ctx.team_id)
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


@router.post("/api/publish/schedule-series")
async def schedule_series(payload: ScheduleSeriesRequest, _: None = Depends(_require_auth)):
    from datetime import date as date_type

    logger.info("schedule-series: draft_id=%r date=%r slots=%r", payload.draft_id, payload.date, payload.slots)
    draft = await get_draft(payload.draft_id)
    if not draft:
        logger.warning("schedule-series: draft NOT FOUND, draft_id=%r (len=%d)", payload.draft_id, len(payload.draft_id))
        raise HTTPException(status_code=404, detail="draft_not_found")
    if draft.kind != "threads_series":
        logger.warning("schedule-series: wrong kind %r for draft %s", draft.kind, payload.draft_id)
        raise HTTPException(status_code=400, detail="draft_kind_mismatch")
    if draft.status != "approved":
        logger.warning("schedule-series: wrong status %r for draft %s", draft.status, payload.draft_id)
        raise HTTPException(status_code=400, detail="draft_must_be_approved")

    try:
        pub_date = date_type.fromisoformat(payload.date)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid_date_format")

    p = dict(draft.payload or {})
    posts = list(p.get("threads_posts", []))
    now = datetime.now(timezone.utc)

    scheduled: list[dict] = []
    for post in posts:
        if post["slot"] not in payload.slots:
            continue
        time_str = post.get("scheduled_time", "09:00")
        try:
            h, m = map(int, time_str.split(":"))
        except ValueError:
            continue
        scheduled_at = datetime(pub_date.year, pub_date.month, pub_date.day, h, m, tzinfo=timezone.utc)
        if scheduled_at <= now:
            logger.info(
                "schedule-series: skipping expired slot %s (scheduled_at=%s <= now=%s)",
                post["slot"], scheduled_at.isoformat(), now.isoformat(),
            )
            continue
        post["status"] = "scheduled"
        scheduled.append({"slot": post["slot"], "scheduled_at": scheduled_at.isoformat()})

    p["threads_posts"] = posts

    if scheduled:
        earliest = min(s["scheduled_at"] for s in scheduled)
        await update_draft(
            payload.draft_id,
            payload=p,
            status="scheduled",
            scheduled_at=datetime.fromisoformat(earliest),
        )
    else:
        await update_draft(payload.draft_id, payload=p)

    logger.info(
        "schedule-series: draft=%s date=%s scheduled_count=%d",
        payload.draft_id, payload.date, len(scheduled),
    )
    return {"draft_id": payload.draft_id, "scheduled": scheduled}


@router.get("/api/publish/history")
async def publish_history(limit: int = 50, ctx: TeamContext = Depends(_resolve_team_context)):
    logs = await list_all_logs(limit=limit, team_id=ctx.team_id)
    return {"items": logs}


# Dynamic route MUST come after all static /api/publish/* routes
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


# ── Metrics ───────────────────────────────────────────────────────────────


@router.get("/api/drafts/{draft_id}/metrics")
async def draft_metrics(draft_id: str, _: None = Depends(_require_auth)):
    """Return latest engagement metrics for a published draft."""
    from bot.services.post_metrics_store import get_latest_metrics

    draft = await get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="draft_not_found")
    metrics = await get_latest_metrics(draft_id)
    return {"draft_id": draft_id, "metrics": metrics}


@router.get("/api/drafts/{draft_id}/metrics/history")
async def draft_metrics_history(
    draft_id: str,
    platform: str = "threads",
    _: None = Depends(_require_auth),
):
    """Return metrics history (all snapshots) for engagement trend."""
    from bot.services.post_metrics_store import get_metrics_history

    history = await get_metrics_history(draft_id, platform)
    return {"draft_id": draft_id, "platform": platform, "history": history}


@router.post("/api/drafts/{draft_id}/metrics/refresh")
async def refresh_draft_metrics(draft_id: str, _: None = Depends(_require_auth)):
    """Manually trigger a fresh metrics fetch for a draft."""
    from bot.services.metrics_fetcher import fetch_metrics_for_draft

    draft = await get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="draft_not_found")
    if draft.status != "published":
        raise HTTPException(status_code=400, detail="draft_not_published")
    result = await fetch_metrics_for_draft(draft_id)
    return {"draft_id": draft_id, "metrics": result}


# ── SSE stream for real-time publish status updates ─────────────────────

def _publish_sse_msg(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.get("/api/drafts/{draft_id}/publish-stream")
async def publish_status_stream(draft_id: str, _: str = Depends(_resolve_sse_auth)):
    """Server-Sent Events stream that pushes publish status updates."""

    async def _event_generator():
        for _ in range(20):  # max ~60 seconds
            draft = await get_draft(draft_id)
            if not draft:
                yield _publish_sse_msg({"error": "not_found"})
                return
            logs = await list_logs(draft_id)
            remote_status = await check_status(draft_id)
            all_done = logs and all(
                l.get("status") in ("success", "failed") for l in logs
            )
            yield _publish_sse_msg({
                "draft_id": draft_id,
                "logs": logs,
                "remote_status": remote_status,
                "done": all_done,
            })
            if all_done:
                return
            await asyncio.sleep(3)

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )
