"""Wraps a BaseCollector with circuit breaker + cached fallback + signal persistence."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from analytics.base import BaseCollector, SourceResult, TrendItem
from analytics.trend_signal_store import (
    get_cached_signals,
    get_health_row,
    save_signals,
    set_circuit_open_until,
    update_health,
)

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 60  # seconds


class ResilientCollector:
    """Wraps a BaseCollector with circuit breaker + cached fallback."""

    def __init__(
        self,
        collector: BaseCollector,
        max_failures: int = 3,
        cooldown_minutes: int = 60,
        timeout_seconds: int = _DEFAULT_TIMEOUT,
    ):
        self._collector = collector
        self._max_failures = max_failures
        self._cooldown_minutes = cooldown_minutes
        self._timeout = timeout_seconds

    @property
    def source_key(self) -> str:
        return self._collector.source_key

    async def collect(self) -> SourceResult:
        """Collect with resilience: circuit breaker + cache fallback + signal persistence."""
        now = datetime.now(timezone.utc)

        # --- circuit breaker check ---
        health = await get_health_row(self.source_key)
        if health is not None:
            open_until = health.circuit_open_until
            # SQLite may return naive datetimes — normalise for comparison
            if open_until is not None and open_until.tzinfo is None:
                open_until = open_until.replace(tzinfo=timezone.utc)
            if (
                health.consecutive_failures >= self._max_failures
                and open_until is not None
                and open_until > now
            ):
                logger.info(
                    "Circuit open for %s until %s — returning cached",
                    self.source_key,
                    health.circuit_open_until.isoformat(),
                )
                return await self._cached_fallback()

        # --- attempt live collection ---
        try:
            result: SourceResult = await asyncio.wait_for(
                self._collector.collect(), timeout=self._timeout
            )
        except asyncio.TimeoutError:
            return await self._handle_failure(f"Timeout after {self._timeout}s")
        except Exception as exc:  # noqa: BLE001
            return await self._handle_failure(str(exc))

        if result.ok:
            await update_health(self.source_key, success=True)
            await save_signals(self.source_key, result.items)
            return result

        # Collector returned a result with an error or no items
        if result.error:
            return await self._handle_failure(result.error)

        # No items, no error — just empty; still treat as success (source has nothing)
        await update_health(self.source_key, success=True)
        return result

    async def _handle_failure(self, error: str) -> SourceResult:
        logger.warning("Collector %s failed: %s", self.source_key, error)
        await update_health(self.source_key, success=False, error=error)
        open_until = datetime.now(timezone.utc) + timedelta(minutes=self._cooldown_minutes)
        await set_circuit_open_until(self.source_key, open_until)
        return await self._cached_fallback()

    async def _cached_fallback(self) -> SourceResult:
        """Return last known good signals as a SourceResult."""
        cached = await get_cached_signals(self.source_key)
        if not cached:
            return SourceResult(
                source_name=self._collector.source_name,
                source_key=self.source_key,
                icon=self._collector.icon,
                items=[],
                error="circuit open, no cache",
            )
        items = [
            TrendItem(
                title=sig.keyword,
                url=sig.items_json.get("url", ""),
                score=sig.items_json.get("score", ""),
                extra=sig.items_json.get("extra", ""),
                summary=sig.items_json.get("summary", ""),
            )
            for sig in cached
        ]
        logger.info("Returning %d cached items for %s", len(items), self.source_key)
        return SourceResult(
            source_name=self._collector.source_name,
            source_key=self.source_key,
            icon=self._collector.icon,
            items=items,
        )
