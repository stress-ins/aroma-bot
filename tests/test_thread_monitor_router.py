"""Tests for miniapp/api/routers/thread_monitor.py — all four endpoints."""
from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from bot.services.tracked_threads_store import (
    save_tracked_thread,
    update_thread_scoring,
)


AUTH_HEADERS = {"X-Telegram-Init-Data": "user=%7B%22id%22%3A62912125%7D&hash=test"}


@pytest.fixture(autouse=True)
def _bypass_auth(monkeypatch):
    os.environ["AROMA_BYPASS_AUTH"] = "1"
    yield
    os.environ.pop("AROMA_BYPASS_AUTH", None)


@pytest.fixture()
async def client():
    from miniapp_server import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


# ── helpers ──────────────────────────────────────────────────────────────────


async def _seed_thread(
    thread_id: str,
    *,
    text: str = "Sample thread text",
    relevance_score: float = 0.5,
    status: str = "new",
    suggested_action: str = "reply",
    ai_summary: str = "",
    topic_tags: list[str] | None = None,
) -> None:
    await save_tracked_thread(
        thread_id,
        platform="threads",
        source="mention",
        author_username="testuser",
        text=text,
        permalink=f"https://threads.net/t/{thread_id}",
        keyword_matched="aroma",
        like_count=10,
        reply_count=3,
    )
    await update_thread_scoring(
        thread_id,
        relevance_score=relevance_score,
        suggested_action=suggested_action,
        ai_summary=ai_summary,
        topic_tags=topic_tags or [],
    )
    if status != "new":
        from bot.services.tracked_threads_store import update_tracked_status
        await update_tracked_status(thread_id, status)


# ── GET /api/thread-monitor/threads ─────────────────────────────────────────


class TestGetMonitoredThreads:
    async def test_empty_list(self, client):
        resp = await client.get(
            "/api/thread-monitor/threads", headers=AUTH_HEADERS
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    async def test_returns_seeded_threads(self, client):
        await _seed_thread("t1", relevance_score=0.8)
        await _seed_thread("t2", relevance_score=0.3)

        resp = await client.get(
            "/api/thread-monitor/threads", headers=AUTH_HEADERS
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        # ordered by relevance_score desc
        assert data["items"][0]["thread_id"] == "t1"
        assert data["items"][1]["thread_id"] == "t2"

    async def test_filter_by_status(self, client):
        await _seed_thread("t-new", status="new")
        await _seed_thread("t-replied", status="replied")

        resp = await client.get(
            "/api/thread-monitor/threads?status=replied",
            headers=AUTH_HEADERS,
        )
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["thread_id"] == "t-replied"

    async def test_filter_by_min_score(self, client):
        await _seed_thread("t-low", relevance_score=0.2)
        await _seed_thread("t-high", relevance_score=0.9)

        resp = await client.get(
            "/api/thread-monitor/threads?min_score=0.5",
            headers=AUTH_HEADERS,
        )
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["thread_id"] == "t-high"

    async def test_limit_param(self, client):
        for i in range(5):
            await _seed_thread(f"t-lim-{i}", relevance_score=0.5 + i * 0.01)

        resp = await client.get(
            "/api/thread-monitor/threads?limit=2",
            headers=AUTH_HEADERS,
        )
        data = resp.json()
        assert data["total"] == 2

    async def test_serialised_fields_present(self, client):
        await _seed_thread(
            "t-fields",
            text="Full thread",
            relevance_score=0.7,
            suggested_action="reply",
            ai_summary="Summary here",
            topic_tags=["wellness", "aroma"],
        )

        resp = await client.get(
            "/api/thread-monitor/threads", headers=AUTH_HEADERS
        )
        item = resp.json()["items"][0]
        expected_keys = {
            "thread_id", "platform", "source", "author_username", "text",
            "permalink", "root_text", "keyword_matched", "like_count",
            "reply_count", "relevance_score", "suggested_action",
            "ai_summary", "content_angle", "topic_tags", "status",
            "found_at", "acted_at",
        }
        assert expected_keys.issubset(item.keys())
        assert item["topic_tags"] == ["wellness", "aroma"]
        assert item["suggested_action"] == "reply"

    async def test_requires_auth(self, client):
        os.environ.pop("AROMA_BYPASS_AUTH", None)
        resp = await client.get("/api/thread-monitor/threads")
        assert resp.status_code == 403


# ── GET /api/thread-monitor/summary ─────────────────────────────────────────


class TestGetMonitorSummary:
    async def test_empty_summary(self, client):
        resp = await client.get(
            "/api/thread-monitor/summary", headers=AUTH_HEADERS
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["new"] == 0
        assert data["replied"] == 0

    async def test_counts_by_status(self, client):
        await _seed_thread("s1", status="new")
        await _seed_thread("s2", status="new")
        await _seed_thread("s3", status="replied")
        await _seed_thread("s4", status="dismissed")

        resp = await client.get(
            "/api/thread-monitor/summary", headers=AUTH_HEADERS
        )
        data = resp.json()
        assert data["total"] == 4
        assert data["new"] == 2
        assert data["replied"] == 1
        assert data["dismissed"] == 1
        assert data["reviewed"] == 0
        assert data["content_created"] == 0

    async def test_requires_auth(self, client):
        os.environ.pop("AROMA_BYPASS_AUTH", None)
        resp = await client.get("/api/thread-monitor/summary")
        assert resp.status_code == 403


# ── POST /api/thread-monitor/threads/{thread_id}/action ─────────────────────


class TestThreadAction:
    async def test_dismiss(self, client):
        await _seed_thread("a1")

        resp = await client.post(
            "/api/thread-monitor/threads/a1/action",
            json={"action": "dismiss"},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["status"] == "dismissed"

    async def test_mark_replied(self, client):
        await _seed_thread("a2")

        resp = await client.post(
            "/api/thread-monitor/threads/a2/action",
            json={"action": "mark_replied"},
            headers=AUTH_HEADERS,
        )
        data = resp.json()
        assert data["status"] == "replied"

    async def test_create_content(self, client):
        await _seed_thread("a3")

        resp = await client.post(
            "/api/thread-monitor/threads/a3/action",
            json={"action": "create_content"},
            headers=AUTH_HEADERS,
        )
        data = resp.json()
        assert data["status"] == "content_created"

    async def test_review(self, client):
        await _seed_thread("a4")

        resp = await client.post(
            "/api/thread-monitor/threads/a4/action",
            json={"action": "review"},
            headers=AUTH_HEADERS,
        )
        data = resp.json()
        assert data["status"] == "reviewed"

    async def test_unknown_action_passthrough(self, client):
        await _seed_thread("a5")

        resp = await client.post(
            "/api/thread-monitor/threads/a5/action",
            json={"action": "custom_status"},
            headers=AUTH_HEADERS,
        )
        data = resp.json()
        assert data["status"] == "custom_status"

    async def test_status_reflected_in_list(self, client):
        await _seed_thread("a6")

        await client.post(
            "/api/thread-monitor/threads/a6/action",
            json={"action": "dismiss"},
            headers=AUTH_HEADERS,
        )

        resp = await client.get(
            "/api/thread-monitor/threads?status=dismissed",
            headers=AUTH_HEADERS,
        )
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["thread_id"] == "a6"

    async def test_requires_auth(self, client):
        os.environ.pop("AROMA_BYPASS_AUTH", None)
        resp = await client.post(
            "/api/thread-monitor/threads/x/action",
            json={"action": "dismiss"},
        )
        assert resp.status_code == 403


# ── POST /api/thread-monitor/refresh ────────────────────────────────────────


class TestRefreshMonitor:
    async def test_refresh_returns_count(self, client, monkeypatch):
        async def _mock_run():
            return 5

        monkeypatch.setattr(
            "bot.services.thread_monitor.run_thread_monitor", _mock_run
        )

        resp = await client.post(
            "/api/thread-monitor/refresh", headers=AUTH_HEADERS
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["relevant_count"] == 5

    async def test_refresh_returns_zero(self, client, monkeypatch):
        async def _mock_run():
            return 0

        monkeypatch.setattr(
            "bot.services.thread_monitor.run_thread_monitor", _mock_run
        )

        resp = await client.post(
            "/api/thread-monitor/refresh", headers=AUTH_HEADERS
        )
        data = resp.json()
        assert data["relevant_count"] == 0

    async def test_requires_auth(self, client):
        os.environ.pop("AROMA_BYPASS_AUTH", None)
        resp = await client.post("/api/thread-monitor/refresh")
        assert resp.status_code == 403
