"""Tests for Meta (Instagram & Threads) webhook endpoints."""
from __future__ import annotations

import hashlib
import hmac
import json
import os

import pytest
from httpx import AsyncClient, ASGITransport


VERIFY_TOKEN = "test-meta-verify-token"
IG_APP_SECRET = "test-ig-secret"
THREADS_APP_SECRET = "test-threads-secret"
WEBHOOK_SECRET = "test-webhook-secret-123"


def _sign_payload(body: bytes, secret: str) -> str:
    """Create X-Hub-Signature-256 header value."""
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


@pytest.fixture(autouse=True)
def patch_settings(monkeypatch):
    import config
    monkeypatch.setattr(config.settings, "meta_webhook_verify_token", VERIFY_TOKEN)
    monkeypatch.setattr(config.settings, "instagram_app_secret", IG_APP_SECRET)
    monkeypatch.setattr(config.settings, "threads_app_secret", THREADS_APP_SECRET)
    monkeypatch.setattr(config.settings, "n8n_webhook_secret", WEBHOOK_SECRET)
    os.environ["AROMA_BYPASS_AUTH"] = "1"
    yield
    os.environ.pop("AROMA_BYPASS_AUTH", None)


@pytest.fixture()
async def oauth_client():
    """Client for the OAuth callback app (threads_oauth_callback)."""
    from threads_oauth_callback import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture()
async def miniapp_client(tmp_path, monkeypatch):
    """Client for the miniapp (mentions ingest API) with temp DB."""
    db_path = tmp_path / "test.db"
    from db.models import Base
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()

    import db.session as sess
    test_engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)
    test_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    monkeypatch.setattr(sess, "AsyncSessionLocal", test_factory)

    from miniapp_server import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    await test_engine.dispose()


# ---------------------------------------------------------------------------
# Verification (GET) tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_instagram_verify_correct_token(oauth_client):
    resp = await oauth_client.get(
        "/webhooks/instagram",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": VERIFY_TOKEN,
            "hub.challenge": "challenge123",
        },
    )
    assert resp.status_code == 200
    assert resp.text == "challenge123"


@pytest.mark.asyncio
async def test_instagram_verify_wrong_token(oauth_client):
    resp = await oauth_client.get(
        "/webhooks/instagram",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong-token",
            "hub.challenge": "challenge123",
        },
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_threads_verify_correct_token(oauth_client):
    resp = await oauth_client.get(
        "/webhooks/threads",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": VERIFY_TOKEN,
            "hub.challenge": "threads-challenge-456",
        },
    )
    assert resp.status_code == 200
    assert resp.text == "threads-challenge-456"


@pytest.mark.asyncio
async def test_threads_verify_wrong_token(oauth_client):
    resp = await oauth_client.get(
        "/webhooks/threads",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong",
            "hub.challenge": "abc",
        },
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Payload (POST) tests — signature validation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_instagram_webhook_valid_signature(oauth_client):
    payload = {
        "object": "instagram",
        "entry": [
            {
                "id": "123",
                "changes": [
                    {
                        "field": "comments",
                        "value": {
                            "id": "comment-001",
                            "text": "Great post about aromatherapy!",
                            "from": {"username": "test_user", "name": "Test"},
                        },
                    }
                ],
            }
        ],
    }
    body = json.dumps(payload).encode()
    sig = _sign_payload(body, IG_APP_SECRET)
    resp = await oauth_client.post(
        "/webhooks/instagram",
        content=body,
        headers={"Content-Type": "application/json", "x-hub-signature-256": sig},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_instagram_webhook_invalid_signature(oauth_client):
    body = b'{"object":"instagram","entry":[]}'
    resp = await oauth_client.post(
        "/webhooks/instagram",
        content=body,
        headers={"Content-Type": "application/json", "x-hub-signature-256": "sha256=invalid"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_threads_webhook_valid_signature(oauth_client):
    payload = {
        "object": "threads",
        "entry": [
            {
                "id": "456",
                "changes": [
                    {
                        "field": "replies",
                        "value": {
                            "id": "reply-001",
                            "text": "Interesting thread!",
                            "from": {"username": "threads_user", "name": "TU"},
                        },
                    }
                ],
            }
        ],
    }
    body = json.dumps(payload).encode()
    sig = _sign_payload(body, THREADS_APP_SECRET)
    resp = await oauth_client.post(
        "/webhooks/threads",
        content=body,
        headers={"Content-Type": "application/json", "x-hub-signature-256": sig},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_threads_webhook_invalid_signature(oauth_client):
    body = b'{"object":"threads","entry":[]}'
    resp = await oauth_client.post(
        "/webhooks/threads",
        content=body,
        headers={"Content-Type": "application/json", "x-hub-signature-256": "sha256=bad"},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# End-to-end: webhook → ingest → mention created
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_webhook_creates_mention_via_ingest(miniapp_client):
    """Verify that _parse_meta_webhook_entries produces correct payloads."""
    from threads_oauth_callback import _parse_meta_webhook_entries

    payload = {
        "entry": [
            {
                "id": "page-123",
                "changes": [
                    {
                        "field": "mentions",
                        "value": {
                            "id": "mention-e2e-001",
                            "text": "Check out @aromara",
                            "from": {"username": "fan_user", "name": "Fan"},
                        },
                    }
                ],
            }
        ],
    }
    items = _parse_meta_webhook_entries(payload, "instagram")
    assert len(items) == 1
    item = items[0]
    assert item["platform"] == "instagram"
    assert item["external_id"] == "mention-e2e-001"
    assert item["content"] == "Check out @aromara"
    assert item["author_username"] == "fan_user"

    # Ingest via miniapp API
    resp = await miniapp_client.post(
        "/api/mentions/ingest",
        json=item,
        headers={"X-Webhook-Secret": WEBHOOK_SECRET},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "created"

    # Verify mention is actually in DB
    from bot.services.mentions_store import find_mention_by_external_id
    mention = await find_mention_by_external_id("instagram", "mention-e2e-001")
    assert mention is not None
    assert mention.content == "Check out @aromara"
    assert mention.author_username == "fan_user"


@pytest.mark.asyncio
async def test_webhook_handler_awaits_forward(miniapp_client, monkeypatch):
    """Verify webhook handler awaits _forward_to_ingest (not fire-and-forget)."""
    forwarded_items: list[dict] = []

    async def fake_forward(items):
        forwarded_items.extend(items)

    import threads_oauth_callback as mod
    monkeypatch.setattr(mod, "_forward_to_ingest", fake_forward)

    payload = {
        "object": "threads",
        "entry": [
            {
                "id": "789",
                "changes": [
                    {
                        "field": "replies",
                        "value": {
                            "id": "reply-await-test",
                            "text": "Testing await",
                            "from": {"username": "tester", "name": "T"},
                        },
                    }
                ],
            }
        ],
    }
    body = json.dumps(payload).encode()
    sig = _sign_payload(body, THREADS_APP_SECRET)

    from httpx import AsyncClient, ASGITransport
    async with AsyncClient(transport=ASGITransport(app=mod.app), base_url="http://test") as client:
        resp = await client.post(
            "/webhooks/threads",
            content=body,
            headers={"Content-Type": "application/json", "x-hub-signature-256": sig},
        )

    assert resp.status_code == 200
    # Because we await (not create_task), items must be forwarded by the time we get the response
    assert len(forwarded_items) == 1
    assert forwarded_items[0]["external_id"] == "reply-await-test"
