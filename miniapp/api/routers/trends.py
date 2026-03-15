"""Trends API — trigger trend collection and report status (called by n8n)."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from ..auth import _require_webhook_auth

logger = logging.getLogger(__name__)

router = APIRouter()

# In-process state (single-worker uvicorn; for multi-worker use shared DB row)
_collection_status: dict = {
    "status": "idle",
    "started_at": None,
    "finished_at": None,
    "error": None,
}


async def _run_collection() -> None:
    from analytics.aggregator import collect_all
    from formatters.report import build_report
    from cache.store import cache

    _collection_status["status"] = "running"
    _collection_status["started_at"] = datetime.now(timezone.utc).isoformat()
    _collection_status["finished_at"] = None
    _collection_status["error"] = None
    try:
        results = await collect_all()
        ru_report = build_report(results, lang="ru")
        en_report = build_report(results, lang="en")
        cache.set("digest", (ru_report, en_report))
        cache.set("results", results)
        _collection_status["status"] = "done"
    except Exception as exc:
        logger.exception("Trend collection failed")
        _collection_status["status"] = "error"
        _collection_status["error"] = str(exc)
    finally:
        _collection_status["finished_at"] = datetime.now(timezone.utc).isoformat()


@router.post("/api/trends/trigger")
async def trigger_trends(_: None = Depends(_require_webhook_auth)):
    """Trigger trend collection in background (idempotent — skip if already running)."""
    if _collection_status["status"] == "running":
        return {"status": "already_running", "started_at": _collection_status["started_at"]}
    asyncio.create_task(_run_collection())
    return {"status": "started", "started_at": datetime.now(timezone.utc).isoformat()}


@router.get("/api/trends/status")
async def trends_status(_: None = Depends(_require_webhook_auth)):
    return _collection_status
