"""Miniapp API for Threads trend monitoring."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from miniapp.api.auth import _require_auth
from miniapp.api.models import ThreadActionRequest

logger = logging.getLogger(__name__)

router = APIRouter()


def _serialize_thread(t) -> dict:
    return {
        "thread_id": t.thread_id,
        "platform": t.platform,
        "source": t.source,
        "author_username": t.author_username,
        "text": t.text[:400],
        "permalink": t.permalink,
        "root_text": t.root_text[:300] if t.root_text else "",
        "keyword_matched": t.keyword_matched,
        "like_count": t.like_count,
        "reply_count": t.reply_count,
        "relevance_score": t.relevance_score,
        "suggested_action": t.suggested_action,
        "ai_summary": t.ai_summary,
        "content_angle": t.content_angle,
        "topic_tags": t.topic_tags or [],
        "status": t.status,
        "found_at": t.found_at.isoformat() if t.found_at else "",
        "acted_at": t.acted_at.isoformat() if t.acted_at else None,
    }


@router.get("/api/thread-monitor/threads")
async def get_monitored_threads(
    status: str = "",
    min_score: float = 0.0,
    limit: int = 20,
    _: None = Depends(_require_auth),
):
    from bot.services.tracked_threads_store import list_tracked_threads
    threads = await list_tracked_threads(status=status or None, min_score=min_score, limit=limit)
    return {"items": [_serialize_thread(t) for t in threads], "total": len(threads)}


@router.get("/api/thread-monitor/summary")
async def get_monitor_summary(_: None = Depends(_require_auth)):
    from bot.services.tracked_threads_store import count_by_status
    counts = await count_by_status()
    return {
        "total": sum(counts.values()),
        "new": counts.get("new", 0),
        "reviewed": counts.get("reviewed", 0),
        "replied": counts.get("replied", 0),
        "content_created": counts.get("content_created", 0),
        "dismissed": counts.get("dismissed", 0),
    }


@router.post("/api/thread-monitor/threads/{thread_id}/action")
async def thread_action(thread_id: str, body: ThreadActionRequest, _: None = Depends(_require_auth)):
    from bot.services.tracked_threads_store import update_tracked_status
    status_map = {"dismiss": "dismissed", "mark_replied": "replied", "create_content": "content_created", "review": "reviewed"}
    new_status = status_map.get(body.action, body.action)
    await update_tracked_status(thread_id, new_status)
    return {"ok": True, "status": new_status}


@router.post("/api/thread-monitor/refresh")
async def refresh_monitor(_: None = Depends(_require_auth)):
    from bot.services.thread_monitor import run_thread_monitor
    count = await run_thread_monitor()
    return {"ok": True, "relevant_count": count}
