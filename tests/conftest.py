import sys
import importlib
import pkgutil

import pytest
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool
from db.models import Base
import db.session

# ── Replace miniapp lifespan globally to prevent infinite background workers ──
# Must happen at import time (before any test imports miniapp_server.app)

@asynccontextmanager
async def _noop_lifespan(app):
    yield

import miniapp_server  # noqa: E402
miniapp_server.app.router.lifespan_context = _noop_lifespan

# ── Pre-import all modules that bind AsyncSessionLocal at import time ──
# These package prefixes contain modules with `from db.session import AsyncSessionLocal`.
# We import them eagerly so _patch_all_async_sessions can discover and patch them.

_PACKAGES_TO_SCAN = [
    ("bot.services", "bot/services"),
    ("bot.agents", "bot/agents"),
    ("analytics", "analytics"),
    ("miniapp.api.routers", "miniapp/api/routers"),
    ("miniapp.api.generation", "miniapp/api/generation"),
]

for _pkg_name, _pkg_path in _PACKAGES_TO_SCAN:
    try:
        _pkg = importlib.import_module(_pkg_name)
    except ImportError:
        continue
    _search_path = getattr(_pkg, "__path__", None)
    if _search_path is None:
        continue
    for _importer, _name, _ispkg in pkgutil.walk_packages(_search_path, _pkg_name + "."):
        # Skip __main__ modules — they execute CLI entry points at import time
        if _name.endswith(".__main__"):
            continue
        try:
            importlib.import_module(_name)
        except Exception:
            pass


def _patch_all_async_sessions(monkeypatch, session_factory):
    """Patch AsyncSessionLocal in db.session and every module that imported it."""
    monkeypatch.setattr(db.session, "AsyncSessionLocal", session_factory)
    for mod in list(sys.modules.values()):
        if mod is None or mod is db.session:
            continue
        if hasattr(mod, "AsyncSessionLocal"):
            try:
                monkeypatch.setattr(mod, "AsyncSessionLocal", session_factory)
            except (TypeError, AttributeError):
                pass


@pytest.fixture(autouse=True, scope="function")
async def setup_test_db(monkeypatch):
    # Ensure auth bypass works with the new AROMA_ENV guard
    monkeypatch.setenv("AROMA_ENV", "test")

    # Disable rate limiting by default so unrelated tests are not affected.
    # The dedicated test_rate_limit.py overrides this per-test.
    monkeypatch.setenv("AROMA_RATE_LIMIT_DISABLED", "1")

    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

    _patch_all_async_sessions(monkeypatch, AsyncSessionLocal)

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Clear reference data cache between tests to avoid cross-test leaks
    from bot.services.miniapp_references.cache import invalidate_all
    invalidate_all()

    # Preload brand settings cache so sync callers don't crash
    from bot.services.brand_settings_store import preload_brand_settings
    await preload_brand_settings()

    yield AsyncSessionLocal

    # Cleanup
    await engine.dispose()


@pytest.fixture
def db_session(setup_test_db):
    """Return the patched AsyncSessionLocal for direct use in tests."""
    return setup_test_db
