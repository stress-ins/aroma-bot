"""Tests for inbox API endpoints — Instagram DM conversations and messages."""
from __future__ import annotations

import os
import pytest
from httpx import AsyncClient, ASGITransport


SECRET = "test-webhook-secret-123"
AUTH_HEADERS = {"X-Telegram-Init-Data": "user=%7B%22id%22%3A62912125%7D&hash=test"}
WEBHOOK_HEADERS = {"X-Webhook-Secret": SECRET}


@pytest.fixture(autouse=True)
def patch_inbox_settings(monkeypatch):
    import config
    monkeypatch.setattr(config.settings, "n8n_webhook_secret", SECRET)
    monkeypatch.setenv("AROMA_BYPASS_AUTH", "1")
    yield


@pytest.fixture()
async def client():
    from miniapp_server import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_inbox_list_empty(client):
    resp = await client.get("/api/inbox", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_ingest_dm_creates_conversation(client):
    resp = await client.post(
        "/api/inbox/ingest",
        json={
            "platform": "instagram",
            "participant_id": "user-123",
            "participant_username": "beauty_fan",
            "participant_name": "Beauty Fan",
            "sender_type": "user",
            "content": "Привет! Какое масло лучше для лица?",
            "external_id": "msg-ext-001",
        },
        headers=WEBHOOK_HEADERS,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "created"
    assert "conversation_id" in data
    assert "message_id" in data

    # Verify conversation appears in list
    resp2 = await client.get("/api/inbox", headers=AUTH_HEADERS)
    items = resp2.json()["items"]
    assert len(items) == 1
    assert items[0]["participant_username"] == "beauty_fan"
    assert items[0]["unread_count"] >= 1


@pytest.mark.asyncio
async def test_ingest_dm_deduplication(client):
    payload = {
        "platform": "instagram",
        "participant_id": "user-456",
        "participant_username": "user456",
        "sender_type": "user",
        "content": "Тестовое сообщение",
        "external_id": "dedup-msg-001",
    }
    resp1 = await client.post("/api/inbox/ingest", json=payload, headers=WEBHOOK_HEADERS)
    assert resp1.json()["status"] == "created"

    resp2 = await client.post("/api/inbox/ingest", json=payload, headers=WEBHOOK_HEADERS)
    assert resp2.json()["status"] == "duplicate"


@pytest.mark.asyncio
async def test_get_conversation_with_messages(client):
    resp = await client.post(
        "/api/inbox/ingest",
        json={
            "platform": "instagram",
            "participant_id": "user-789",
            "participant_username": "user789",
            "sender_type": "user",
            "content": "Первое сообщение",
            "external_id": "msg-get-001",
        },
        headers=WEBHOOK_HEADERS,
    )
    conv_id = resp.json()["conversation_id"]

    resp2 = await client.get(f"/api/inbox/{conv_id}", headers=AUTH_HEADERS)
    assert resp2.status_code == 200
    data = resp2.json()
    assert data["conversation_id"] == conv_id
    assert "messages" in data
    assert len(data["messages"]) == 1
    assert data["messages"][0]["content"] == "Первое сообщение"


@pytest.mark.asyncio
async def test_reply_to_conversation(client, monkeypatch):
    resp = await client.post(
        "/api/inbox/ingest",
        json={
            "platform": "instagram",
            "participant_id": "user-reply-test",
            "participant_username": "reply_test",
            "sender_type": "user",
            "content": "Вопрос о маслах",
            "external_id": "msg-reply-001",
        },
        headers=WEBHOOK_HEADERS,
    )
    conv_id = resp.json()["conversation_id"]

    # Mock Instagram send
    import miniapp.api.routers.inbox as inbox_mod
    calls = []
    async def mock_send(recipient_id, text, team_id=None):
        calls.append(("send", recipient_id, text))
    monkeypatch.setattr(inbox_mod, "_send_instagram_message", mock_send)

    resp2 = await client.post(
        f"/api/inbox/{conv_id}/reply",
        json={"text": "Рекомендую масло лаванды!"},
        headers=AUTH_HEADERS,
    )
    assert resp2.status_code == 200
    data = resp2.json()
    assert data["sent"] is True
    assert len(calls) == 1

    resp3 = await client.get(f"/api/inbox/{conv_id}", headers=AUTH_HEADERS)
    messages = resp3.json()["messages"]
    assert len(messages) == 2
    assert messages[1]["sender_type"] == "business"


@pytest.mark.asyncio
async def test_archive_conversation(client):
    resp = await client.post(
        "/api/inbox/ingest",
        json={
            "platform": "instagram",
            "participant_id": "user-archive-test",
            "participant_username": "archive_test",
            "sender_type": "user",
            "content": "Тест архивации",
            "external_id": "msg-archive-001",
        },
        headers=WEBHOOK_HEADERS,
    )
    conv_id = resp.json()["conversation_id"]

    resp2 = await client.post(f"/api/inbox/{conv_id}/archive", headers=AUTH_HEADERS)
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "archived"

    resp3 = await client.get("/api/inbox?status=active", headers=AUTH_HEADERS)
    active_ids = [c["conversation_id"] for c in resp3.json()["items"]]
    assert conv_id not in active_ids

    resp4 = await client.get("/api/inbox?status=archived", headers=AUTH_HEADERS)
    archived_ids = [c["conversation_id"] for c in resp4.json()["items"]]
    assert conv_id in archived_ids


@pytest.mark.asyncio
async def test_conversation_not_found(client):
    resp = await client.get("/api/inbox/nonexistent-id", headers=AUTH_HEADERS)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_ingest_unauthorized(client):
    resp = await client.post(
        "/api/inbox/ingest",
        json={
            "platform": "instagram",
            "participant_id": "hacker",
            "sender_type": "user",
            "content": "spam",
        },
        headers={"X-Webhook-Secret": "wrong-secret"},
    )
    assert resp.status_code == 403
