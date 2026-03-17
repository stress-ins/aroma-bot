"""Tests for blend agents and blends_store."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from db.models import Base
import bot.services.blends_store as bs_mod
from bot.services.blends_store import get_blend, list_blends, upsert_blend, search_by_ingredient


@pytest_asyncio.fixture()
async def in_memory_db(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(bs_mod, "AsyncSessionLocal", factory)
    yield factory
    await engine.dispose()


# ------------------------------------------------------------------
# blends_store
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upsert_and_get_blend(in_memory_db):
    rec = await upsert_blend(
        slug="sleep-mix",
        name="Смесь для сна",
        goal="улучшение сна",
        ingredients=[{"oil_slug": "lavanda", "ratio": 3.0, "unit": "капли"}],
        indications="бессонница, тревожность",
        contraindications="беременность",
    )
    assert rec.slug == "sleep-mix"
    assert len(rec.ingredients) == 1

    fetched = await get_blend("sleep-mix")
    assert fetched is not None
    assert fetched.name == "Смесь для сна"


@pytest.mark.asyncio
async def test_list_blends_by_goal(in_memory_db):
    await upsert_blend(slug="b1", name="Blend 1", goal="сон")
    await upsert_blend(slug="b2", name="Blend 2", goal="энергия")
    await upsert_blend(slug="b3", name="Blend 3", goal="глубокий сон")

    results = await list_blends(goal="сон")
    assert len(results) == 2


@pytest.mark.asyncio
async def test_search_by_ingredient(in_memory_db):
    await upsert_blend(
        slug="relax",
        name="Релакс",
        ingredients=[
            {"oil_slug": "lavanda", "ratio": 3.0, "unit": "капли"},
            {"oil_slug": "kedr", "ratio": 2.0, "unit": "капли"},
        ],
    )
    await upsert_blend(
        slug="energy",
        name="Энергия",
        ingredients=[
            {"oil_slug": "limon", "ratio": 4.0, "unit": "капли"},
        ],
    )

    results = await search_by_ingredient("lavanda")
    assert len(results) == 1
    assert results[0].slug == "relax"


@pytest.mark.asyncio
async def test_upsert_updates_existing(in_memory_db):
    await upsert_blend(slug="b1", name="Old Name", goal="old")
    await upsert_blend(slug="b1", name="New Name", goal="new")

    rec = await get_blend("b1")
    assert rec.name == "New Name"
    assert rec.goal == "new"


# ------------------------------------------------------------------
# blend_composer — does not crash with empty oils
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compose_blend_does_not_crash(in_memory_db):
    """CLAUDE.md checkpoint: compose_blend(goal="сон", oils_available=[]) не падает."""
    from bot.agents.blend_composer import compose_blend

    fake_response = json.dumps({
        "name": "Сон",
        "ingredients": [{"oil": "лаванда", "ratio": 3.0, "unit": "капли"}],
        "instructions": "нанести на запястья",
        "contraindications": "нет",
    })

    with (
        patch("bot.agents.blend_composer.get_brand_settings_cached") as mock_bs,
        patch("bot.agents.blend_composer.call_claude", return_value=fake_response),
    ):
        mock_bs.return_value = MagicMock(brand_voice="test voice", forbidden_phrases=[])
        result = await compose_blend(goal="сон", oils_available=[])

    assert "name" in result
    assert "ingredients" in result


# ------------------------------------------------------------------
# symptom_advisor — returns list
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_advise_by_symptom_returns_list(in_memory_db):
    from bot.agents.symptom_advisor import advise_by_symptom

    fake_response = json.dumps([
        {"oil_or_blend": "лаванда", "type": "oil", "reason": "успокаивает", "contraindications": "нет"},
    ])

    with (
        patch("bot.agents.symptom_advisor.get_brand_settings_cached") as mock_bs,
        patch("bot.agents.symptom_advisor.call_claude", return_value=fake_response),
    ):
        mock_bs.return_value = MagicMock(brand_voice="test voice", forbidden_phrases=[])
        result = await advise_by_symptom("бессонница")

    assert isinstance(result, list)
    assert len(result) > 0
    assert "oil_or_blend" in result[0]


# ------------------------------------------------------------------
# compatibility_checker — returns dict with expected keys
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_compatibility_returns_expected_keys(in_memory_db):
    from bot.agents.compatibility_checker import check_compatibility

    fake_response = json.dumps({
        "compatible": True,
        "warnings": [],
        "contraindications": [],
        "synergies": ["лаванда + кедр — усиливают седативный эффект"],
    })

    with (
        patch("bot.agents.compatibility_checker.get_brand_settings_cached") as mock_bs,
        patch("bot.agents.compatibility_checker.call_claude", return_value=fake_response),
    ):
        mock_bs.return_value = MagicMock(brand_voice="test voice", forbidden_phrases=[])
        result = await check_compatibility(["лаванда", "кедр"])

    assert "compatible" in result
    assert "warnings" in result
    assert "contraindications" in result
    assert "synergies" in result
