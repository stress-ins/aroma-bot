"""Tests for bot.services.analytics_store — event logging and aggregation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

import bot.services.analytics_store as analytics_mod


# ──────────────────────────────────────────────────────
# log_event
# ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_log_event_creates_record(setup_test_db):
    event = await analytics_mod.log_event(
        team_id=None,
        telegram_id=12345,
        event_name="page_view",
        category="navigation",
        data={"mode": "content", "tab": "drafts"},
        session_id="sess-1",
    )
    assert event.id is not None
    assert event.event_name == "page_view"
    assert event.event_category == "navigation"
    assert event.event_data == {"mode": "content", "tab": "drafts"}
    assert event.session_id == "sess-1"


@pytest.mark.asyncio
async def test_log_events_batch(setup_test_db):
    count = await analytics_mod.log_events_batch(
        [
            {"event_name": "page_view", "category": "navigation", "data": {}, "session_id": "s1"},
            {"event_name": "draft_create", "category": "content", "data": {"kind": "post"}, "session_id": "s1"},
        ],
        team_id=None,
        telegram_id=12345,
    )
    assert count == 2


@pytest.mark.asyncio
async def test_log_events_batch_empty(setup_test_db):
    count = await analytics_mod.log_events_batch([], team_id=None, telegram_id=12345)
    assert count == 0


# ──────────────────────────────────────────────────────
# get_event_counts
# ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_event_counts(setup_test_db):
    await analytics_mod.log_event(event_name="page_view", category="navigation")
    await analytics_mod.log_event(event_name="page_view", category="navigation")
    await analytics_mod.log_event(event_name="draft_create", category="content")

    total = await analytics_mod.get_event_counts()
    assert total == 3

    pv_count = await analytics_mod.get_event_counts(event_name="page_view")
    assert pv_count == 2


@pytest.mark.asyncio
async def test_get_event_counts_since(setup_test_db):
    await analytics_mod.log_event(event_name="old_event", category="test")
    # All events are created "now", so filtering with a future date returns 0
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    count = await analytics_mod.get_event_counts(since=future)
    assert count == 0


# ──────────────────────────────────────────────────────
# get_popular_events
# ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_popular_events_ordering(setup_test_db):
    for _ in range(5):
        await analytics_mod.log_event(event_name="page_view", category="navigation")
    for _ in range(2):
        await analytics_mod.log_event(event_name="draft_create", category="content")
    await analytics_mod.log_event(event_name="publish", category="content")

    popular = await analytics_mod.get_popular_events(limit=10)
    assert len(popular) == 3
    assert popular[0]["event_name"] == "page_view"
    assert popular[0]["count"] == 5
    assert popular[1]["event_name"] == "draft_create"
    assert popular[1]["count"] == 2


# ──────────────────────────────────────────────────────
# get_feature_usage
# ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_feature_usage(setup_test_db):
    await analytics_mod.log_event(event_name="page_view", category="navigation")
    await analytics_mod.log_event(event_name="search", category="navigation")
    await analytics_mod.log_event(event_name="draft_create", category="content")

    usage = await analytics_mod.get_feature_usage()
    assert usage["navigation"] == 2
    assert usage["content"] == 1


# ──────────────────────────────────────────────────────
# get_daily_active_users
# ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_daily_active_users(setup_test_db):
    await analytics_mod.log_event(event_name="page_view", telegram_id=111)
    await analytics_mod.log_event(event_name="page_view", telegram_id=222)
    await analytics_mod.log_event(event_name="page_view", telegram_id=111)

    dau = await analytics_mod.get_daily_active_users()
    assert len(dau) == 1  # all events same day
    assert dau[0]["count"] == 2  # 2 unique users
