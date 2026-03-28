"""Tests for GET /api/trends/digest endpoint and DigestCache persistence."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from miniapp_server import app


@pytest.mark.asyncio
async def test_digest_returns_not_available_when_empty(setup_test_db):
    """When no digest has been saved, endpoint returns status=not_available."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/trends/digest")
    assert resp.status_code == 200
    data = resp.json()
    assert data == {"status": "not_available"}


@pytest.mark.asyncio
async def test_digest_returns_saved_report(setup_test_db):
    """After saving a digest, endpoint returns ru_report, en_report, generated_at."""
    from bot.services.digest_store import save_digest

    await save_digest("Русский отчет", "English report")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/trends/digest")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ru_report"] == "Русский отчет"
    assert data["en_report"] == "English report"
    assert "generated_at" in data


@pytest.mark.asyncio
async def test_digest_upsert_overwrites(setup_test_db):
    """Saving a digest twice overwrites the previous one (upsert)."""
    from bot.services.digest_store import save_digest, get_digest

    await save_digest("Первый отчет", "First report")
    await save_digest("Второй отчет", "Second report")

    digest = await get_digest()
    assert digest is not None
    assert digest["ru_report"] == "Второй отчет"
    assert digest["en_report"] == "Second report"


@pytest.mark.asyncio
async def test_digest_store_roundtrip(setup_test_db):
    """save_digest -> get_digest roundtrip works correctly."""
    from bot.services.digest_store import save_digest, get_digest

    assert await get_digest() is None

    await save_digest("RU", "EN")
    result = await get_digest()
    assert result is not None
    assert result["ru_report"] == "RU"
    assert result["en_report"] == "EN"
    assert "generated_at" in result
