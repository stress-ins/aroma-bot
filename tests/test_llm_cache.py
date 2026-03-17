"""Tests for LLM response cache (bot/services/llm_cache.py) and prompt corrections."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# Cache key determinism
# ---------------------------------------------------------------------------

def test_make_cache_key_deterministic():
    from bot.services.llm_cache import make_cache_key
    k1 = make_cache_key("blend", brief="test", effects="a,b")
    k2 = make_cache_key("blend", effects="a,b", brief="test")  # different order
    assert k1 == k2, "Cache key should be deterministic regardless of param order"


def test_make_cache_key_different_types():
    from bot.services.llm_cache import make_cache_key
    k1 = make_cache_key("blend", brief="test")
    k2 = make_cache_key("reco", brief="test")
    assert k1 != k2


# ---------------------------------------------------------------------------
# Cache get/set/expiry (requires DB)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cache_set_and_get():
    from bot.services.llm_cache import get_cached, set_cached
    key = "test_key_set_get"
    await set_cached(key, "test", {"answer": 42}, ttl_hours=1)
    result = await get_cached(key)
    assert result is not None
    assert result["answer"] == 42


@pytest.mark.asyncio
async def test_cache_miss():
    from bot.services.llm_cache import get_cached
    result = await get_cached("nonexistent_key_xyz")
    assert result is None


@pytest.mark.asyncio
async def test_cache_hit_count():
    from bot.services.llm_cache import get_cached, set_cached
    from sqlalchemy import select
    from db.models import LlmCacheModel
    from db.session import AsyncSessionLocal

    key = "test_key_hits"
    await set_cached(key, "test", {"v": 1}, ttl_hours=1)
    await get_cached(key)
    await get_cached(key)
    async with AsyncSessionLocal() as session:
        row = (await session.execute(
            select(LlmCacheModel).where(LlmCacheModel.cache_key == key)
        )).scalar_one_or_none()
        assert row is not None
        assert row.hit_count == 2


@pytest.mark.asyncio
async def test_cache_expiry():
    from bot.services.llm_cache import get_cached, set_cached
    from sqlalchemy import select
    from db.models import LlmCacheModel
    from db.session import AsyncSessionLocal

    key = "test_key_expired"
    await set_cached(key, "test", {"v": 1}, ttl_hours=1)

    # Manually expire the row
    async with AsyncSessionLocal() as session:
        row = (await session.execute(
            select(LlmCacheModel).where(LlmCacheModel.cache_key == key)
        )).scalar_one()
        row.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        await session.commit()

    result = await get_cached(key)
    assert result is None, "Expired cache entries should return None"


# ---------------------------------------------------------------------------
# Prompt corrections: no "аромалампа" in prompts
# ---------------------------------------------------------------------------

def test_blend_prompt_has_diffuser_rule():
    from bot.agents.aromatherapy_expert import _CONSTRUCT_BLEND_PROMPT
    assert "аромалампу" in _CONSTRUCT_BLEND_PROMPT
    assert "диффузор" in _CONSTRUCT_BLEND_PROMPT


def test_recommendation_prompt_has_diffuser_rule():
    from bot.agents.recommendation_agent import _SYSTEM_PROMPT
    assert "аромалампу" in _SYSTEM_PROMPT
    assert "диффузор" in _SYSTEM_PROMPT


def test_daily_oil_prompt_has_diffuser_rule():
    """Verify the daily oil generation prompt includes application rules."""
    import bot.services.daily_oil as daily_oil
    import inspect
    source = inspect.getsource(daily_oil._generate_fact_and_practice)
    assert "аромалампу" in source
    assert "диффузор" in source
    assert "ладонь" in source
