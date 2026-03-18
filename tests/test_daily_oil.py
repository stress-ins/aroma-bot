"""Tests for Daily Oil of the Day feature."""

from __future__ import annotations

import pytest

from db.models import AromaCardModel, BrandSettingsModel, DailyOilModel, UserProfile


@pytest.mark.asyncio
async def test_select_daily_oil_creates_row(setup_test_db, monkeypatch):
    """select_daily_oil creates a new DailyOilModel when none exists."""
    from db.session import AsyncSessionLocal

    # Seed one aroma card
    async with AsyncSessionLocal() as session:
        session.add(AromaCardModel(slug="lavender", name="Лаванда", category="aroma"))
        await session.commit()

    import bot.services.daily_oil as mod
    monkeypatch.setattr(mod, "AsyncSessionLocal", AsyncSessionLocal)

    # Mock external APIs and Claude calls
    async def _mock_ctx(target_date):
        return {"date": target_date, "weekday": "вторник", "season": "весна",
                "month_name": "март", "city": "Москва", "is_weekend": False}

    monkeypatch.setattr(mod, "_build_day_context", _mock_ctx)
    monkeypatch.setattr(mod, "_pick_oil_via_claude",
                        lambda candidates, ctx: (candidates[0], "тестовая причина"))
    monkeypatch.setattr(mod, "_generate_fact_and_practice",
                        lambda name, ctx=None: ("Fun fact", "Daily practice"))

    oil = await mod.select_daily_oil("2026-03-17")
    assert oil.slug == "lavender"
    assert oil.name == "Лаванда"
    assert oil.fact == "Fun fact"
    assert oil.daily_practice == "Daily practice"
    assert oil.reason == "тестовая причина"


@pytest.mark.asyncio
async def test_select_daily_oil_idempotent(setup_test_db, monkeypatch):
    """Calling select_daily_oil twice for same date returns same row."""
    from db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        session.add(AromaCardModel(slug="tea-tree", name="Чайное дерево", category="aroma"))
        await session.commit()

    import bot.services.daily_oil as mod
    monkeypatch.setattr(mod, "AsyncSessionLocal", AsyncSessionLocal)

    async def _mock_ctx(target_date):
        return {"date": target_date, "weekday": "среда", "season": "весна",
                "month_name": "март", "city": "Москва", "is_weekend": False}

    monkeypatch.setattr(mod, "_build_day_context", _mock_ctx)
    monkeypatch.setattr(mod, "_pick_oil_via_claude",
                        lambda candidates, ctx: (candidates[0], "причина"))
    monkeypatch.setattr(mod, "_generate_fact_and_practice",
                        lambda name, ctx=None: ("Fact", "Practice"))

    oil1 = await mod.select_daily_oil("2026-03-17")
    oil2 = await mod.select_daily_oil("2026-03-17")
    assert oil1.id == oil2.id


@pytest.mark.asyncio
async def test_get_daily_oil_returns_none_when_empty(setup_test_db, monkeypatch):
    """get_daily_oil returns None when no row exists for today."""
    from db.session import AsyncSessionLocal
    import bot.services.daily_oil as mod
    monkeypatch.setattr(mod, "AsyncSessionLocal", AsyncSessionLocal)

    result = await mod.get_daily_oil("2026-01-01")
    assert result is None


@pytest.mark.asyncio
async def test_get_daily_oil_returns_dict_with_reason(setup_test_db, monkeypatch):
    """get_daily_oil returns a dict with expected keys including reason."""
    from db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        session.add(DailyOilModel(
            date="2026-03-17", slug="eucalyptus", name="Эвкалипт",
            fact="A fact", daily_practice="A practice",
            reason="Весна — время очищения", context={"season": "весна"},
        ))
        await session.commit()

    import bot.services.daily_oil as mod
    monkeypatch.setattr(mod, "AsyncSessionLocal", AsyncSessionLocal)

    result = await mod.get_daily_oil("2026-03-17")
    assert result is not None
    assert result["slug"] == "eucalyptus"
    assert result["fact"] == "A fact"
    assert result["daily_practice"] == "A practice"
    assert result["reason"] == "Весна — время очищения"
    assert result["context"]["season"] == "весна"


@pytest.mark.asyncio
async def test_get_subscribed_user_ids(setup_test_db, monkeypatch):
    """get_subscribed_user_ids returns only subscribed users."""
    from db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        session.add(UserProfile(telegram_id=111, daily_oil_subscribed=True))
        session.add(UserProfile(telegram_id=222, daily_oil_subscribed=False))
        session.add(UserProfile(telegram_id=333, daily_oil_subscribed=True))
        await session.commit()

    import bot.services.daily_oil as mod
    monkeypatch.setattr(mod, "AsyncSessionLocal", AsyncSessionLocal)

    ids = await mod.get_subscribed_user_ids()
    assert set(ids) == {111, 333}


@pytest.mark.asyncio
async def test_toggle_subscription(setup_test_db, monkeypatch):
    """toggle_subscription flips the flag."""
    from db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        session.add(UserProfile(telegram_id=111, daily_oil_subscribed=True))
        await session.commit()

    import bot.services.daily_oil as mod
    monkeypatch.setattr(mod, "AsyncSessionLocal", AsyncSessionLocal)

    new_val = await mod.toggle_subscription(111)
    assert new_val is False

    new_val2 = await mod.toggle_subscription(111)
    assert new_val2 is True


# ---------------------------------------------------------------------------
# Contextual selection tests
# ---------------------------------------------------------------------------


def test_get_season():
    """_get_season returns correct season for each month."""
    from bot.services.daily_oil import _get_season
    assert _get_season(1) == "зима"
    assert _get_season(3) == "весна"
    assert _get_season(7) == "лето"
    assert _get_season(10) == "осень"


def test_score_candidate_season_boost():
    """Cards with season-relevant properties score higher."""
    from bot.services.daily_oil import _score_candidate

    card_tonic = AromaCardModel(
        slug="rosemary", name="Розмарин", category="aroma",
        payload={"therapeutic_properties": ["тонизирующее"], "psychological_properties": []},
    )
    card_warming = AromaCardModel(
        slug="cinnamon", name="Корица", category="aroma",
        payload={"therapeutic_properties": ["согревающее"], "psychological_properties": []},
    )

    ctx_spring = {"season": "весна", "is_weekend": False}
    assert _score_candidate(card_tonic, ctx_spring) > _score_candidate(card_warming, ctx_spring)


def test_score_candidate_weekend_boost():
    """Relaxing oils score higher on weekends."""
    from bot.services.daily_oil import _score_candidate

    card_relax = AromaCardModel(
        slug="lavender", name="Лаванда", category="aroma",
        payload={"therapeutic_properties": [], "psychological_properties": ["расслабление"]},
    )
    card_focus = AromaCardModel(
        slug="rosemary", name="Розмарин", category="aroma",
        payload={"therapeutic_properties": [], "psychological_properties": ["концентрация"]},
    )

    ctx_weekend = {"season": "весна", "is_weekend": True}
    assert _score_candidate(card_relax, ctx_weekend) > _score_candidate(card_focus, ctx_weekend)


def test_score_candidate_empty_payload():
    """Cards with empty payload get score 0."""
    from bot.services.daily_oil import _score_candidate

    card = AromaCardModel(slug="unknown", name="Unknown", category="aroma", payload={})
    ctx = {"season": "весна", "is_weekend": False}
    assert _score_candidate(card, ctx) == 0.0


def test_prefilter_returns_max_candidates():
    """_prefilter_candidates returns at most max_count cards."""
    from bot.services.daily_oil import _prefilter_candidates

    cards = [
        AromaCardModel(
            slug=f"oil-{i}", name=f"Oil {i}", category="aroma",
            payload={"therapeutic_properties": ["тонизирующее"], "psychological_properties": []},
        )
        for i in range(20)
    ]
    ctx = {"season": "весна", "is_weekend": False}
    result = _prefilter_candidates(cards, ctx, max_count=5)
    assert len(result) == 5


def test_prefilter_fallback_random_on_zero_scores():
    """If all scores are 0, returns random sample."""
    from bot.services.daily_oil import _prefilter_candidates

    cards = [
        AromaCardModel(slug=f"oil-{i}", name=f"Oil {i}", category="aroma", payload={})
        for i in range(15)
    ]
    ctx = {"season": "весна", "is_weekend": False}
    result = _prefilter_candidates(cards, ctx, max_count=10)
    assert len(result) == 10


def test_weather_code_to_text():
    """_weather_code_to_text maps codes correctly."""
    from bot.services.daily_oil import _weather_code_to_text
    assert _weather_code_to_text(0) == "ясно"
    assert _weather_code_to_text(2) == "облачно"
    assert _weather_code_to_text(61) == "дождь"
    assert _weather_code_to_text(73) == "снег"
    assert _weather_code_to_text(95) == "гроза"


@pytest.mark.asyncio
async def test_build_day_context_fallback(setup_test_db, monkeypatch):
    """_build_day_context works even when APIs fail."""
    from db.session import AsyncSessionLocal
    import bot.services.daily_oil as mod
    import bot.services.brand_settings_store as bss
    monkeypatch.setattr(mod, "AsyncSessionLocal", AsyncSessionLocal)
    monkeypatch.setattr(bss, "AsyncSessionLocal", AsyncSessionLocal)

    # Mock APIs to fail
    async def _fail_weather(lat, lon):
        return None

    async def _fail_kp():
        return None

    monkeypatch.setattr(mod, "_fetch_weather", _fail_weather)
    monkeypatch.setattr(mod, "_fetch_kp_index", _fail_kp)

    ctx = await mod._build_day_context("2026-03-18")
    assert ctx["date"] == "2026-03-18"
    assert ctx["weekday"] == "среда"
    assert ctx["season"] == "весна"
    assert ctx["city"] == "Москва"
    assert "weather" not in ctx
    assert "solar_activity" not in ctx
