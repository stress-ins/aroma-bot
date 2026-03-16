"""Tests for personal oil recommendations."""
from __future__ import annotations
import json
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from db.models import AromaCardModel
@pytest.fixture(autouse=True)
def _bypass_auth(monkeypatch):
    monkeypatch.setenv("AROMA_BYPASS_AUTH", "1")
@pytest.fixture()
def _seed_aromas(setup_test_db):
    import asyncio
    from db.session import AsyncSessionLocal
    async def _insert():
        async with AsyncSessionLocal() as session:
            for slug, name in [("lavender", "Лаванда"), ("peppermint", "Мята"), ("bergamot", "Бергамот")]:
                session.add(AromaCardModel(slug=slug, name=name, category="aroma", source_type="herb", payload={"name_ru": name}))
            await session.commit()
    asyncio.get_event_loop().run_until_complete(_insert())
_MOCK = json.dumps({"recommendations": [{"slug": "lavender", "name_ru": "Лаванда", "reason": "Снимает стресс.", "daily_practice": "3 капли."}, {"slug": "bergamot", "name_ru": "Бергамот", "reason": "Настроение.", "daily_practice": "1 каплю."}, {"slug": "peppermint", "name_ru": "Мята", "reason": "Головная боль.", "daily_practice": "Вдыхайте."}], "general_advice": "Регулярно."})
@pytest.mark.asyncio
async def test_personal_recommendations_endpoint(_seed_aromas):
    with patch("bot.services.claude_client.call_claude", return_value=_MOCK):
        from miniapp_server import app
        client = TestClient(app)
        resp = client.post("/api/recommendations/personal", json={"mood": "stressed", "goal": "relax"}, headers={"X-Telegram-Init-Data": "user=%7B%22id%22%3A12345%7D&auth_date=9999999999&hash=abc"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["recommendations"]) == 3
        assert data["recommendations"][0]["card"] is not None
@pytest.mark.asyncio
async def test_personal_recommendations_validation():
    from miniapp_server import app
    client = TestClient(app)
    resp = client.post("/api/recommendations/personal", json={"mood": "", "goal": ""}, headers={"X-Telegram-Init-Data": "user=%7B%22id%22%3A12345%7D&auth_date=9999999999&hash=abc"})
    assert resp.status_code == 400
@pytest.mark.asyncio
async def test_recommend_oils_sync_parses_response():
    with patch("bot.services.claude_client.call_claude", return_value=_MOCK):
        from bot.agents.recommendation_agent import recommend_oils_sync
        result = recommend_oils_sync("stressed", "relax", [], [], "", "- lavender (herb)")
        assert len(result["recommendations"]) == 3
