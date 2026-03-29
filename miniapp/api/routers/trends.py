"""Trends API — trigger trend collection and report status (called by n8n)."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from ..auth import _require_webhook_auth
from ..schemas import TrendIntelligenceResponse

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
        # Persist digest to DB so it survives restarts
        try:
            from bot.services.digest_store import save_digest
            await save_digest(ru_report, en_report)
        except Exception:
            logger.exception("Failed to persist digest to DB")
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


@router.get("/api/trends/health")
async def trends_health():
    """Return collector health status (circuit breaker state)."""
    from analytics.trend_signal_store import get_health_status

    return await get_health_status()


@router.get("/api/trends/intelligence", response_model=TrendIntelligenceResponse)
async def trends_intelligence():
    """Return enriched trend intelligence report."""
    from analytics.trend_intelligence import generate_trend_report

    return await generate_trend_report()


@router.get("/api/trends/digest")
async def trends_digest():
    """Return the latest cached digest report from DB."""
    from bot.services.digest_store import get_digest

    digest = await get_digest()
    if digest is None:
        return {"status": "not_available"}
    return digest


@router.post("/api/trends/enrich")
async def trigger_enrichment(_: None = Depends(_require_webhook_auth)):
    """Trigger trend signal enrichment (called by n8n or manually)."""
    from analytics.signal_enricher import enrich_signals

    count = await enrich_signals()
    return {"status": "done", "enriched": count}
