"""Tests for Daily Oil of the Day feature."""

from __future__ import annotations

import pytest

from db.models import AromaCardModel, DailyOilModel, UserProfile


@pytest.mark.asyncio
async def test_select_daily_oil_creates_row(setup_test_db, monkeypatch):
    """select_daily_oil creates a new DailyOilModel when none exists."""
    from db.session import AsyncSessionLocal

    # Seed one aroma card
    async with AsyncSessionLocal() as session:
        session.add(AromaCardModel(slug="lavender", name="Лаванда", category="aroma"))
        await session.commit()

    # Monkeypatch Claude call
    monkeypatch.setattr(
        "bot.services.daily_oil._generate_fact_and_practice",
        lambda name: ("Fun fact", "Daily practice"),
    )
    import bot.services.daily_oil as mod
    monkeypatch.setattr(mod, "AsyncSessionLocal", AsyncSessionLocal)

    oil = await mod.select_daily_oil("2026-03-17")
    assert oil.slug == "lavender"
    assert oil.name == "Лаванда"
    assert oil.fact == "Fun fact"
    assert oil.daily_practice == "Daily practice"


@pytest.mark.asyncio
async def test_select_daily_oil_idempotent(setup_test_db, monkeypatch):
    """Calling select_daily_oil twice for same date returns same row."""
    from db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        session.add(AromaCardModel(slug="tea-tree", name="Чайное дерево", category="aroma"))
        await session.commit()

    monkeypatch.setattr(
        "bot.services.daily_oil._generate_fact_and_practice",
        lambda name: ("Fact", "Practice"),
    )
    import bot.services.daily_oil as mod
    monkeypatch.setattr(mod, "AsyncSessionLocal", AsyncSessionLocal)

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
async def test_get_daily_oil_returns_dict(setup_test_db, monkeypatch):
    """get_daily_oil returns a dict with expected keys."""
    from db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        session.add(DailyOilModel(
            date="2026-03-17", slug="eucalyptus", name="Эвкалипт",
            fact="A fact", daily_practice="A practice",
        ))
        await session.commit()

    import bot.services.daily_oil as mod
    monkeypatch.setattr(mod, "AsyncSessionLocal", AsyncSessionLocal)

    result = await mod.get_daily_oil("2026-03-17")
    assert result is not None
    assert result["slug"] == "eucalyptus"
    assert result["fact"] == "A fact"
    assert result["daily_practice"] == "A practice"


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
