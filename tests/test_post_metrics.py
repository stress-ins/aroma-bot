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
async def test_get_latest_metrics_batch():
    from bot.services.post_metrics_store import save_metrics, get_latest_metrics_batch

    d1 = "test_batch_001"
    d2 = "test_batch_002"
    d3 = "test_batch_003"

    await save_metrics(d1, "threads", "ext_1", {"views": 100, "likes": 5, "replies": 2})
    await save_metrics(d1, "threads", "ext_1", {"views": 200, "likes": 10, "replies": 3})
    await save_metrics(d1, "instagram", "ext_2", {"impressions": 300, "likes": 20, "comments": 4})
    await save_metrics(d2, "threads", "ext_3", {"views": 50, "likes": 1})

    batch = await get_latest_metrics_batch([d1, d2, d3])
    assert d1 in batch
    assert d2 in batch
    assert d3 not in batch  # no metrics saved for d3

    # d1: threads (200 views, 10 likes, 3 replies) + instagram (300 impressions/views, 20 likes, 4 comments)
    assert batch[d1]["likes"] == 30  # 10 + 20
    assert batch[d1]["views"] == 500  # 200 + 300
    assert batch[d1]["replies"] == 3
    assert batch[d1]["comments"] == 4

    # d2: only threads
    assert batch[d2]["likes"] == 1
    assert batch[d2]["views"] == 50


@pytest.mark.asyncio
async def test_get_latest_metrics_batch_empty():
    from bot.services.post_metrics_store import get_latest_metrics_batch

    batch = await get_latest_metrics_batch([])
    assert batch == {}

    batch2 = await get_latest_metrics_batch(["nonexistent"])
    assert batch2 == {}


@pytest.mark.asyncio
async def test_list_drafts_needing_fetch_empty():
    from bot.services.post_metrics_store import list_drafts_needing_fetch

    result = await list_drafts_needing_fetch()
    assert isinstance(result, list)
    assert len(result) == 0
