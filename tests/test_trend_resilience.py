"""Tests for trend resilience layer: circuit breaker, cached fallback, signal persistence."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from analytics.base import BaseCollector, SourceResult, TrendItem
from analytics.resilient_collector import ResilientCollector
from analytics.trend_signal_store import (
    get_cached_signals,
    get_health_status,
    save_signals,
    update_health,
)
from db.models import CollectorHealth
from db.session import AsyncSessionLocal


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _OKCollector(BaseCollector):
    source_name = "Test OK"
    source_key = "test_ok"
    icon = "T"

    async def collect(self) -> SourceResult:
        return SourceResult(
            source_name=self.source_name,
            source_key=self.source_key,
            icon=self.icon,
            items=[TrendItem(title="lavender", score="42")],
        )


class _FailCollector(BaseCollector):
    source_name = "Test Fail"
    source_key = "test_fail"
    icon = "F"

    async def collect(self) -> SourceResult:
        raise RuntimeError("boom")


class _SlowCollector(BaseCollector):
    source_name = "Test Slow"
    source_key = "test_slow"
    icon = "S"

    async def collect(self) -> SourceResult:
        await asyncio.sleep(999)
        return SourceResult(
            source_name=self.source_name,
            source_key=self.source_key,
            icon=self.icon,
            items=[],
        )


class _ErrorResultCollector(BaseCollector):
    source_name = "Test ErrResult"
    source_key = "test_errresult"
    icon = "E"

    async def collect(self) -> SourceResult:
        return SourceResult(
            source_name=self.source_name,
            source_key=self.source_key,
            icon=self.icon,
            items=[],
            error="upstream 503",
        )


# ---------------------------------------------------------------------------
# Signal persistence
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_save_and_get_cached_signals():
    items = [
        TrendItem(title="lavender", score="42", url="https://example.com"),
        TrendItem(title="peppermint", score="10"),
    ]
    await save_signals("test_src", items)

    cached = await get_cached_signals("test_src", max_age_hours=1)
    assert len(cached) == 2
    keywords = {s.keyword for s in cached}
    assert keywords == {"lavender", "peppermint"}


@pytest.mark.asyncio
async def test_get_cached_signals_empty():
    cached = await get_cached_signals("nonexistent", max_age_hours=1)
    assert cached == []


# ---------------------------------------------------------------------------
# Health tracking
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_health_success():
    await update_health("src_a", success=True)
    status = await get_health_status()
    row = next(s for s in status if s["source_key"] == "src_a")
    assert row["consecutive_failures"] == 0
    assert row["last_success"] is not None


@pytest.mark.asyncio
async def test_update_health_failure_increments():
    await update_health("src_b", success=False, error="fail1")
    await update_health("src_b", success=False, error="fail2")
    status = await get_health_status()
    row = next(s for s in status if s["source_key"] == "src_b")
    assert row["consecutive_failures"] == 2
    assert row["last_error"] == "fail2"


@pytest.mark.asyncio
async def test_update_health_success_resets_failures():
    await update_health("src_c", success=False, error="oops")
    await update_health("src_c", success=True)
    status = await get_health_status()
    row = next(s for s in status if s["source_key"] == "src_c")
    assert row["consecutive_failures"] == 0
    assert row["last_error"] == ""


# ---------------------------------------------------------------------------
# ResilientCollector — successful collection
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_resilient_success_persists_signals():
    rc = ResilientCollector(_OKCollector(), max_failures=3)
    result = await rc.collect()

    assert result.ok
    assert len(result.items) == 1
    assert result.items[0].title == "lavender"

    # Signals persisted
    cached = await get_cached_signals("test_ok", max_age_hours=1)
    assert len(cached) == 1

    # Health updated
    status = await get_health_status()
    row = next(s for s in status if s["source_key"] == "test_ok")
    assert row["consecutive_failures"] == 0


# ---------------------------------------------------------------------------
# ResilientCollector — circuit breaker
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_circuit_breaker_opens_after_max_failures():
    rc = ResilientCollector(_FailCollector(), max_failures=3, cooldown_minutes=60)

    # 3 failures to open circuit
    for _ in range(3):
        result = await rc.collect()
        assert not result.ok

    status = await get_health_status()
    row = next(s for s in status if s["source_key"] == "test_fail")
    assert row["consecutive_failures"] == 3
    assert row["circuit_open_until"] is not None


@pytest.mark.asyncio
async def test_circuit_open_returns_cached_fallback():
    # Seed cache first
    await save_signals("test_fail2", [TrendItem(title="cached_item", score="99")])

    # Create a fail collector with source_key matching cached data
    class _Fail2(BaseCollector):
        source_name = "Fail2"
        source_key = "test_fail2"
        icon = "F"

        async def collect(self) -> SourceResult:
            raise RuntimeError("boom")

    rc = ResilientCollector(_Fail2(), max_failures=2, cooldown_minutes=60)

    # Trigger failures to open circuit
    await rc.collect()
    await rc.collect()

    # Next call should use cache (circuit is open)
    result = await rc.collect()
    assert result.ok
    assert len(result.items) == 1
    assert result.items[0].title == "cached_item"


# ---------------------------------------------------------------------------
# ResilientCollector — timeout
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_timeout_triggers_failure():
    rc = ResilientCollector(_SlowCollector(), max_failures=3, timeout_seconds=1)
    result = await rc.collect()
    assert not result.ok or result.error == ""  # either no cache or empty

    status = await get_health_status()
    row = next(s for s in status if s["source_key"] == "test_slow")
    assert row["consecutive_failures"] == 1
    assert "Timeout" in row["last_error"]


# ---------------------------------------------------------------------------
# ResilientCollector — error in SourceResult
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_error_result_handled_as_failure():
    rc = ResilientCollector(_ErrorResultCollector(), max_failures=3)
    result = await rc.collect()

    status = await get_health_status()
    row = next(s for s in status if s["source_key"] == "test_errresult")
    assert row["consecutive_failures"] == 1
    assert "503" in row["last_error"]
