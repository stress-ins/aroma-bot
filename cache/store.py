from __future__ import annotations

import time
from typing import Any

from config import settings


class TTLCache:
    def __init__(self, ttl: int | None = None) -> None:
        self._ttl = ttl or settings.cache_ttl
        self._store: dict[str, tuple[Any, float]] = {}

    def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if time.monotonic() > expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        self._store[key] = (value, time.monotonic() + self._ttl)

    def clear(self) -> None:
        self._store.clear()


# Singleton
cache = TTLCache()
