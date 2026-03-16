"""Tests for post_metrics_store and metrics API endpoints."""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_save_and_get_latest_metrics():
    from bot.services.post_metrics_store import save_metrics, get_latest_metrics

    draft_id = "test_metrics_001"

    # Save two snapshots for threads
    await save_metrics(draft_id, "threads", "ext_1", {"views": 100, "likes": 5})
    await save_metrics(draft_id, "threads", "ext_1", {"views": 200, "likes": 10})
    # Save one for instagram
    await save_metrics(draft_id, "instagram", "ext_2", {"impressions": 300})

    latest = await get_latest_metrics(draft_id)
    assert len(latest) == 2

    by_platform = {m["platform"]: m for m in latest}
    assert by_platform["threads"]["metrics"]["views"] == 200
    assert by_platform["threads"]["metrics"]["likes"] == 10
    assert by_platform["instagram"]["metrics"]["impressions"] == 300


@pytest.mark.asyncio
async def test_get_metrics_history():
    from bot.services.post_metrics_store import save_metrics, get_metrics_history

    draft_id = "test_metrics_002"

    await save_metrics(draft_id, "threads", "ext_1", {"views": 50})
    await save_metrics(draft_id, "threads", "ext_1", {"views": 100})
    await save_metrics(draft_id, "threads", "ext_1", {"views": 150})

    history = await get_metrics_history(draft_id, "threads")
    assert len(history) == 3
    # Newest first
    assert history[0]["metrics"]["views"] == 150
    assert history[2]["metrics"]["views"] == 50


@pytest.mark.asyncio
async def test_list_drafts_needing_fetch_empty():
    from bot.services.post_metrics_store import list_drafts_needing_fetch

    result = await list_drafts_needing_fetch()
    assert isinstance(result, list)
    assert len(result) == 0
