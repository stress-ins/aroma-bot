"""Tests for rate limiting middleware."""
from __future__ import annotations

import json
import os
import urllib.parse

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("AROMA_BYPASS_AUTH", "1")
os.environ.setdefault("AROMA_ENV", "test")

from miniapp.api.rate_limit import reset_limits, is_generation_path


def _make_init_data(user_id: int = 12345) -> str:
    """Build a fake initData string with the given user ID."""
    user_json = json.dumps({"id": user_id})
    return urllib.parse.urlencode({"user": user_json, "auth_date": "1700000000", "hash": "abc"})


@pytest.fixture(autouse=True)
def _clean_limits(monkeypatch):
    """Enable rate limiting and reset counters for each test."""
    monkeypatch.delenv("AROMA_RATE_LIMIT_DISABLED", raising=False)
    reset_limits()
    yield
    reset_limits()


@pytest.fixture
def client():
    from miniapp_server import app
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    return AsyncClient(transport=transport, base_url="http://test")


# ---------------------------------------------------------------------------
# is_generation_path unit tests
# ---------------------------------------------------------------------------

class TestIsGenerationPath:
    def test_generate_content(self):
        assert is_generation_path("/api/generate/content") is True

    def test_generate_carousel(self):
        assert is_generation_path("/api/generate/carousel") is True

    def test_generate_reels(self):
        assert is_generation_path("/api/generate/reels") is True

    def test_regenerate_slides(self):
        assert is_generation_path("/api/carousel/abc123/slides/0/regenerate") is True

    def test_regenerate_all_frames(self):
        assert is_generation_path("/api/reels/abc123/frames/regenerate-all") is True

    def test_storyboard_regenerate(self):
        assert is_generation_path("/api/reels/abc123/storyboard/regenerate") is True

    def test_plan_generate(self):
        assert is_generation_path("/api/plans/abc123/generate") is True

    def test_trends_cards_generate(self):
        assert is_generation_path("/api/trends/cards/generate") is True

    def test_regular_get(self):
        assert is_generation_path("/api/drafts") is False

    def test_regular_post(self):
        assert is_generation_path("/api/drafts/abc/approve") is False

    def test_non_api(self):
        assert is_generation_path("/static/app.js") is False

    def test_inbox_generate_reply(self):
        assert is_generation_path("/api/inbox/conv123/generate-reply") is True

    def test_mentions_generate_replies(self):
        assert is_generation_path("/api/mentions/m1/generate-replies") is True


# ---------------------------------------------------------------------------
# Integration tests -- middleware returns 429
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rate_limit_default_returns_429(client):
    """After 60 POST requests, the 61st should get 429."""
    headers = {"x-telegram-init-data": _make_init_data(99001)}
    # Use a non-generation POST endpoint
    for i in range(60):
        resp = await client.post("/api/tone/analyze", headers=headers, json={"text": "hi"})
        assert resp.status_code != 429, f"Got 429 on request #{i + 1}"

    # 61st should be rate-limited
    resp = await client.post("/api/tone/analyze", headers=headers, json={"text": "hi"})
    assert resp.status_code == 429
    body = resp.json()
    assert body["detail"]["error"] == "rate_limit"
    assert "retry_after" in body["detail"]
    assert resp.headers.get("retry-after") is not None


@pytest.mark.asyncio
async def test_rate_limit_generation_returns_429(client):
    """Generation endpoints have a stricter limit (20/min)."""
    headers = {"x-telegram-init-data": _make_init_data(99002)}
    for i in range(20):
        resp = await client.post(
            "/api/generate/content", headers=headers,
            json={"topic": "test", "format": "carousel"},
        )
        assert resp.status_code != 429, f"Got 429 on request #{i + 1}"

    # 21st should be rate-limited
    resp = await client.post(
        "/api/generate/content", headers=headers,
        json={"topic": "test", "format": "carousel"},
    )
    assert resp.status_code == 429


@pytest.mark.asyncio
async def test_rate_limit_readonly_higher_limit(client):
    """GET endpoints allow 120 req/min."""
    headers = {"x-telegram-init-data": _make_init_data(99003)}
    for i in range(120):
        resp = await client.get("/api/preferences/theme", headers=headers)
        assert resp.status_code != 429, f"Got 429 on GET request #{i + 1}"

    # 121st should be rate-limited
    resp = await client.get("/api/preferences/theme", headers=headers)
    assert resp.status_code == 429


@pytest.mark.asyncio
async def test_rate_limit_per_user_isolation(client):
    """Different users have independent counters."""
    headers_a = {"x-telegram-init-data": _make_init_data(99004)}
    headers_b = {"x-telegram-init-data": _make_init_data(99005)}

    # Exhaust user A's generation limit
    for _ in range(20):
        await client.post("/api/generate/content", headers=headers_a, json={"topic": "t", "format": "carousel"})

    # User A is limited
    resp_a = await client.post("/api/generate/content", headers=headers_a, json={"topic": "t", "format": "carousel"})
    assert resp_a.status_code == 429

    # User B should NOT be limited
    resp_b = await client.post("/api/generate/content", headers=headers_b, json={"topic": "t", "format": "carousel"})
    assert resp_b.status_code != 429


@pytest.mark.asyncio
async def test_rate_limit_admin_exempt(client, monkeypatch):
    """Allowed team members are exempt from rate limiting."""
    admin_uid = 88888
    monkeypatch.setenv("ADMIN_TELEGRAM_CHAT_ID", str(admin_uid))
    # Re-initialize exempt IDs
    from miniapp.api import rate_limit as rl_mod
    rl_mod._EXEMPT_IDS = {f"tg:{admin_uid}"}

    headers = {"x-telegram-init-data": _make_init_data(admin_uid)}
    # Send more than the generation limit — admin should never get 429
    for _ in range(25):
        resp = await client.post("/api/generate/content", headers=headers, json={"topic": "t", "format": "carousel"})
        assert resp.status_code != 429


@pytest.mark.asyncio
async def test_rate_limit_disabled_env(client, monkeypatch):
    """When AROMA_RATE_LIMIT_DISABLED=1, no rate limiting occurs."""
    monkeypatch.setenv("AROMA_RATE_LIMIT_DISABLED", "1")
    headers = {"x-telegram-init-data": _make_init_data(99006)}

    # Send more than the generation limit
    for _ in range(25):
        resp = await client.post("/api/generate/content", headers=headers, json={"topic": "t", "format": "carousel"})
        assert resp.status_code != 429


@pytest.mark.asyncio
async def test_static_paths_not_rate_limited(client):
    """Static file requests should bypass rate limiting."""
    for _ in range(200):
        resp = await client.get("/static/js/core.js")
        assert resp.status_code != 429


@pytest.mark.asyncio
async def test_429_response_format(client):
    """Verify 429 body matches the format expected by core.js fetchJson."""
    headers = {"x-telegram-init-data": _make_init_data(99007)}
    # Exhaust generation limit quickly
    for _ in range(20):
        await client.post("/api/generate/content", headers=headers, json={"topic": "t", "format": "carousel"})

    resp = await client.post("/api/generate/content", headers=headers, json={"topic": "t", "format": "carousel"})
    assert resp.status_code == 429
    body = resp.json()
    # Must have detail.error and detail.retry_after
    assert isinstance(body, dict)
    assert "detail" in body
    detail = body["detail"]
    assert detail["error"] == "rate_limit"
    assert isinstance(detail["retry_after"], int)
    assert detail["retry_after"] > 0
