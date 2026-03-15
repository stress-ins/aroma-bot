"""Tests for bot.services.brand_settings_store."""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from db.models import Base, BrandSettingsModel
import bot.services.brand_settings_store as bs_mod


@pytest_asyncio.fixture()
async def in_memory_db(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(bs_mod, "AsyncSessionLocal", factory)
    # Reset cache before each test
    bs_mod._cache = None
    yield factory
    await engine.dispose()


# ------------------------------------------------------------------
# get_brand_settings
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_brand_settings_creates_default(in_memory_db):
    row = await bs_mod.get_brand_settings()
    assert row is not None
    assert row.brand_voice == bs_mod._DEFAULT_BRAND_VOICE
    assert isinstance(row.forbidden_phrases, list)
    assert len(row.forbidden_phrases) > 0


@pytest.mark.asyncio
async def test_get_brand_settings_returns_existing(in_memory_db):
    # First call creates, second returns existing
    first = await bs_mod.get_brand_settings()
    second = await bs_mod.get_brand_settings()
    assert first.id == second.id


# ------------------------------------------------------------------
# update_brand_settings
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_brand_settings(in_memory_db):
    await bs_mod.get_brand_settings()  # seed default
    updated = await bs_mod.update_brand_settings(brand_voice="new voice")
    assert updated.brand_voice == "new voice"

    # Verify persistence
    row = await bs_mod.get_brand_settings()
    assert row.brand_voice == "new voice"


@pytest.mark.asyncio
async def test_update_forbidden_phrases(in_memory_db):
    await bs_mod.get_brand_settings()
    updated = await bs_mod.update_brand_settings(
        forbidden_phrases=["phrase1", "phrase2"]
    )
    assert updated.forbidden_phrases == ["phrase1", "phrase2"]


# ------------------------------------------------------------------
# Cache
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_preload_populates_cache(in_memory_db):
    assert bs_mod._cache is None
    await bs_mod.preload_brand_settings()
    assert bs_mod._cache is not None
    assert bs_mod._cache.brand_voice == bs_mod._DEFAULT_BRAND_VOICE


def test_get_cached_raises_when_not_loaded():
    bs_mod._cache = None
    with pytest.raises(bs_mod.BrandSettingsNotLoaded):
        bs_mod.get_brand_settings_cached()


@pytest.mark.asyncio
async def test_get_cached_returns_value_after_preload(in_memory_db):
    await bs_mod.preload_brand_settings()
    cached = bs_mod.get_brand_settings_cached()
    assert cached.brand_voice == bs_mod._DEFAULT_BRAND_VOICE


@pytest.mark.asyncio
async def test_update_refreshes_cache(in_memory_db):
    await bs_mod.preload_brand_settings()
    await bs_mod.update_brand_settings(brand_voice="updated")
    cached = bs_mod.get_brand_settings_cached()
    assert cached.brand_voice == "updated"
