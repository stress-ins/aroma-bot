"""Orchestrates fetching engagement metrics for published drafts."""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def fetch_metrics_for_draft(draft_id: str) -> dict[str, dict[str, Any]]:
    """Fetch fresh metrics for all platforms a draft was published to.

    Returns {platform: {metric_name: value, ...}, ...}
    """
    from bot.services.drafts_store import get_draft
    from bot.services.post_metrics_store import save_metrics
    from bot.services.meta_publisher import get_threads_insights, get_instagram_insights

    draft = await get_draft(draft_id)
    if not draft or not draft.external_ids:
        return {}

    results: dict[str, dict[str, Any]] = {}
    ext = draft.external_ids

    # Threads
    threads_id = ext.get("threads")
    if threads_id:
        try:
            metrics = await get_threads_insights(str(threads_id))
            await save_metrics(draft_id, "threads", str(threads_id), metrics)
            results["threads"] = metrics
            logger.info("Threads metrics for %s: %s", draft_id, metrics)
        except Exception as exc:
            logger.warning("Threads insights failed for %s: %s", draft_id, exc)

    # Instagram
    instagram_id = ext.get("instagram")
    if instagram_id:
        try:
            metrics = await get_instagram_insights(str(instagram_id))
            await save_metrics(draft_id, "instagram", str(instagram_id), metrics)
            results["instagram"] = metrics
            logger.info("Instagram metrics for %s: %s", draft_id, metrics)
        except Exception as exc:
            logger.warning("Instagram insights failed for %s: %s", draft_id, exc)

    return results


async def fetch_all_pending_metrics() -> int:
    """Fetch metrics for all recently published drafts that need a refresh.

    Returns the number of drafts processed.
    """
    from bot.services.post_metrics_store import list_drafts_needing_fetch

    drafts = await list_drafts_needing_fetch()
    if not drafts:
        return 0

    count = 0
    for d in drafts:
        try:
            result = await fetch_metrics_for_draft(d["draft_id"])
            if result:
                count += 1
        except Exception as exc:
            logger.error("Metrics fetch error for %s: %s", d["draft_id"], exc)

    return count
