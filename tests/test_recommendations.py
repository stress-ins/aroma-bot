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


_PROTOCOL_MOCK = json.dumps({
    "protocol_name": "Протокол от стресса",
    "protocol_description": "Комплексный протокол для снятия стресса.",
    "oil": {"slug": "lavender", "name_ru": "Лаванда", "reason": "Расслабляет.", "usage": "3 капли в диффузор"},
    "massage": {"slug": "aroma-massage", "name_ru": "Аромамассаж", "reason": "Снимает напряжение.", "duration_min": 30},
    "sound": {"slug": "tibetan-singing-bowl", "name_ru": "Тибетская поющая чаша", "reason": "Медитация.", "duration_min": 15},
    "crystal": {"slug": "amethyst", "name_ru": "Аметист", "reason": "Успокаивает ум.", "placement": "На лоб"},
    "session_plan": [
        {"step": 1, "modality": "oil", "action": "Зажгите диффузор", "duration_min": 5},
        {"step": 2, "modality": "sound", "action": "Поющая чаша", "duration_min": 15},
        {"step": 3, "modality": "massage", "action": "Аромамассаж", "duration_min": 30},
    ],
    "synergy": "Лаванда усиливает эффект массажа.",
    "total_duration_min": 50,
    "general_advice": "Проводите сеанс вечером.",
})


@pytest.fixture()
def _seed_all_categories(setup_test_db):
    import asyncio
    from db.session import AsyncSessionLocal

    async def _insert():
        async with AsyncSessionLocal() as session:
            session.add(AromaCardModel(slug="lavender", name="Лаванда", category="aroma", source_type="herb", payload={"name_ru": "Лаванда"}))
            session.add(AromaCardModel(slug="aroma-massage", name="Аромамассаж", category="massage", source_type="technique", payload={"name_en": "Aromatherapy Massage"}))
            session.add(AromaCardModel(slug="tibetan-singing-bowl", name="Тибетская поющая чаша", category="sound", source_type="instrument", payload={"name_en": "Tibetan Singing Bowl"}))
            session.add(AromaCardModel(slug="amethyst", name="Аметист", category="crystal", source_type="quartz", payload={"name_en": "Amethyst"}))
            await session.commit()
    asyncio.get_event_loop().run_until_complete(_insert())


@pytest.mark.asyncio
async def test_protocol_recommendations_endpoint(_seed_all_categories):
    with patch("bot.services.claude_client.call_claude", return_value=_PROTOCOL_MOCK):
        from miniapp_server import app
        client = TestClient(app)
        resp = client.post(
            "/api/recommendations/protocol",
            json={"concern": "stress", "body_zone": "full_body", "goal": "relax"},
            headers={"X-Telegram-Init-Data": "user=%7B%22id%22%3A12345%7D&auth_date=9999999999&hash=abc"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["protocol_name"] == "Протокол от стресса"
        assert data["oil"]["slug"] == "lavender"
        assert data["oil"]["card"] is not None
        assert data["massage"]["slug"] == "aroma-massage"
        assert data["massage"]["card"] is not None
        assert data["sound"]["slug"] == "tibetan-singing-bowl"
        assert data["crystal"]["slug"] == "amethyst"
        assert len(data["session_plan"]) == 3
        assert data["total_duration_min"] == 50


@pytest.mark.asyncio
async def test_protocol_recommendations_validation():
    from miniapp_server import app
    client = TestClient(app)
    resp = client.post(
        "/api/recommendations/protocol",
        json={"concern": ""},
        headers={"X-Telegram-Init-Data": "user=%7B%22id%22%3A12345%7D&auth_date=9999999999&hash=abc"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_protocol_agent_parses_response():
    with patch("bot.services.claude_client.call_claude", return_value=_PROTOCOL_MOCK):
        from bot.agents.protocol_recommendation_agent import recommend_protocol_sync
        result = recommend_protocol_sync("stress", "full_body", "relax", "all", "", "context")
        assert result["protocol_name"] == "Протокол от стресса"
        assert result["oil"]["slug"] == "lavender"
        assert len(result["session_plan"]) == 3
