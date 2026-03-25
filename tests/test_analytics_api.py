"""Tests for analytics API endpoints."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from miniapp_server import app

# Dummy initData for auth bypass (AROMA_BYPASS_AUTH=1 + AROMA_ENV=test)
AUTH_HEADERS = {"X-Telegram-Init-Data": "user=%7B%22id%22%3A12345%7D&hash=test"}


@pytest.mark.asyncio
async def test_post_analytics_event(setup_test_db, monkeypatch):
    monkeypatch.setenv("AROMA_BYPASS_AUTH", "1")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/analytics/event",
            json={
                "events": [
                    {"event_name": "page_view", "category": "navigation", "data": {"tab": "drafts"}, "session_id": "s1"},
                    {"event_name": "draft_create", "category": "content", "data": {"kind": "post"}, "session_id": "s1"},
                ],
            },
            headers=AUTH_HEADERS,
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["count"] == 2


@pytest.mark.asyncio
async def test_get_analytics_summary(setup_test_db, monkeypatch):
    monkeypatch.setenv("AROMA_BYPASS_AUTH", "1")
    import bot.services.analytics_store as store

    await store.log_event(event_name="page_view", category="navigation", telegram_id=111)
    await store.log_event(event_name="draft_create", category="content", telegram_id=222)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/analytics/summary?days=7")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_events_7d"] == 2
    assert isinstance(body["top_events_7d"], list)
    assert isinstance(body["feature_usage_7d"], dict)


@pytest.mark.asyncio
async def test_get_analytics_events_list(setup_test_db, monkeypatch):
    monkeypatch.setenv("AROMA_BYPASS_AUTH", "1")
    import bot.services.analytics_store as store

    await store.log_event(event_name="page_view", category="navigation")
    await store.log_event(event_name="publish", category="content")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/analytics/events?days=7&limit=10")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["events"]) == 2
    assert body["events"][0]["event_name"] in ("page_view", "publish")
