"""In-memory TTL cache for reference card data.

Uses ``cachetools.TTLCache`` to avoid hitting the database on every request
for reference lists and detail cards.  The cache is keyed by
``(function_name, category)`` for list endpoints and
``(function_name, category, slug)`` for detail endpoints.

Cache is automatically invalidated when reference cards are updated
(see ``invalidate_category``).
"""
from __future__ import annotations

import asyncio
from typing import Any

from cachetools import TTLCache

from config import settings

# Single shared cache instance; maxsize is generous because the number of
# (category x slug) combinations is bounded (< 1000 in practice).
_cache: TTLCache[str, Any] = TTLCache(maxsize=2048, ttl=settings.reference_cache_ttl)
_lock = asyncio.Lock()


def _make_key(*parts: str) -> str:
    return ":".join(parts)


async def get_cached(key: str) -> Any | None:
    """Return cached value or ``None`` if not present / expired."""
    return _cache.get(key)


async def set_cached(key: str, value: Any) -> None:
    """Store a value in cache."""
    _cache[key] = value


def invalidate_category(category: str) -> None:
    """Remove all cached entries for a given category (list + all details)."""
    keys_to_remove = [k for k in _cache if k.startswith(f"list:{category}:") or k.startswith(f"detail:{category}:")]
    for k in keys_to_remove:
        _cache.pop(k, None)


def invalidate_all() -> None:
    """Clear the entire reference cache."""
    _cache.clear()
