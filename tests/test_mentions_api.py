"""Tests for mentions and tokens API endpoints."""
from __future__ import annotations

import os
import pytest
from httpx import AsyncClient, ASGITransport

os.environ.setdefault("AROMA_BYPASS_AUTH", "1")

SECRET = "test-webhook-secret-123"
# Dummy header for _require_auth endpoints (AROMA_BYPASS_AUTH=1 makes _verify_init_data return True)
AUTH_HEADERS = {"X-Telegram-Init-Data": "user=%7B%22id%22%3A62912125%7D&hash=test"}
WEBHOOK_HEADERS = {"X-Webhook-Secret": SECRET}


@pytest.fixture(autouse=True)
def patch_settings(monkeypatch):
    """Patch the singleton settings object for webhook secret + auth bypass."""
    import config
    monkeypatch.setattr(config.settings, "n8n_webhook_secret", SECRET)
    os.environ["AROMA_BYPASS_AUTH"] = "1"
    yield
    os.environ.pop("AROMA_BYPASS_AUTH", None)


@pytest.fixture()
async def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    # Create tables in temp DB
    from db.models import Base
    from sqlalchemy.ext.asyncio import create_async_engine
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()

    # Patch the session factory to use the temp DB
    import db.session as sess
    from sqlalchemy.ext.asyncio import async_sessionmaker
    test_engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)
    test_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    monkeypatch.setattr(sess, "AsyncSessionLocal", test_factory)

    from miniapp_server import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    await test_engine.dispose()


@pytest.mark.asyncio
async def test_ingest_mention(client):
    resp = await client.post(
        "/api/mentions/ingest",
        json={
            "platform": "telegram",
            "external_id": "msg-001",
            "type": "mention",
            "author_username": "testuser",
            "author_name": "Test User",
            "content": "Отличный пост об ароматерапии!",
        },
        headers={"X-Webhook-Secret": SECRET},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "created"
    assert "mention_id" in data


@pytest.mark.asyncio
async def test_ingest_mention_unauthorized(client):
    resp = await client.post(
        "/api/mentions/ingest",
        json={
            "platform": "telegram",
            "external_id": "msg-002",
            "type": "mention",
            "author_username": "hacker",
            "author_name": "Hacker",
            "content": "spam",
        },
        headers={"X-Webhook-Secret": "wrong-secret"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_mentions(client):
    # Ingest two mentions
    for i in range(2):
        await client.post(
            "/api/mentions/ingest",
            json={
                "platform": "threads",
                "external_id": f"post-{i}",
                "type": "mention",
                "author_username": f"user{i}",
                "author_name": f"User {i}",
                "content": f"Message {i}",
            },
            headers=WEBHOOK_HEADERS,
        )

    resp = await client.get("/api/mentions?platform=threads&status=pending", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) >= 2


@pytest.mark.asyncio
async def test_generate_replies_no_api_key(client, monkeypatch):
    """Without ANTHROPIC_API_KEY, generate-replies should return empty list (no crash)."""
    import config
    monkeypatch.setattr(config.settings, "anthropic_api_key", "")

    # Ingest first
    resp = await client.post(
        "/api/mentions/ingest",
        json={
            "platform": "threads",
            "external_id": "post-gen",
            "type": "mention",
            "author_username": "gen_user",
            "author_name": "Gen User",
            "content": "Расскажи больше об эфирных маслах",
        },
        headers={"X-Webhook-Secret": SECRET},
    )
    mention_id = resp.json()["mention_id"]

    resp2 = await client.post(f"/api/mentions/{mention_id}/generate-replies", headers=AUTH_HEADERS)
    assert resp2.status_code == 200
    data = resp2.json()
    assert "replies" in data


@pytest.mark.asyncio
async def test_ignore_mention(client):
    resp = await client.post(
        "/api/mentions/ingest",
        json={
            "platform": "instagram",
            "external_id": "ig-001",
            "type": "comment",
            "author_username": "spammer",
            "author_name": "Spammer",
            "content": "Buy followers now!",
        },
        headers={"X-Webhook-Secret": SECRET},
    )
    mention_id = resp.json()["mention_id"]

    resp2 = await client.patch(f"/api/mentions/{mention_id}/ignore", headers=AUTH_HEADERS)
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "ignored"

    # Verify it's ignored in list (won't appear in pending filter)
    resp3 = await client.get(f"/api/mentions/{mention_id}", headers=AUTH_HEADERS)
    assert resp3.json()["status"] == "ignored"


@pytest.mark.asyncio
async def test_token_status_empty(client):
    resp = await client.get("/api/tokens/status", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert "tokens" in data
    assert isinstance(data["tokens"], list)


@pytest.mark.asyncio
async def test_token_update_and_status(client):
    resp = await client.patch(
        "/api/tokens/threads",
        json={"access_token": "my-token-abc", "expires_at": None},
        headers={"X-Webhook-Secret": SECRET},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["platform"] == "threads"
    assert data["has_token"] is True
