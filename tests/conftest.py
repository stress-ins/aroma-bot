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
import bot.services.drafts_store
import bot.services.plans_store
import bot.services.miniapp_references
import bot.services.miniapp_references.common
import bot.services.miniapp_references.aroma
import bot.services.miniapp_references.blend
import bot.services.miniapp_references.crystal
import bot.services.miniapp_references.symptom
import bot.services.draft_revisions_store
import bot.services.kb_context_builder
import bot.services.post_metrics_store
import bot.services.daily_oil
import analytics.trend_signal_store
import analytics.signal_enricher
import analytics.trend_intelligence
import bot.services.llm_cache
import bot.services.brand_settings_store
import bot.services.subscription_store
import bot.services.blends_store
import bot.services.saved_blends_store
import bot.services.mentions_store
import bot.services.inbox_store
import bot.services.cost_stats_store
import bot.services.publish_log_store
import bot.services.tracked_threads_store
import bot.services.team_store
import bot.services.video_task_store
import bot.services.social_trends_store
import bot.services.past_publications_store
import bot.services.content_analytics
import bot.services.analytics_store
import bot.services.digest_store
import miniapp.api.routers.plans
import miniapp.api.routers.misc
# Note: miniapp.api.routers.analytics uses local import from db.session (already patched)


@pytest.fixture(autouse=True, scope="function")
async def setup_test_db(monkeypatch):
    # Ensure auth bypass works with the new AROMA_ENV guard
    monkeypatch.setenv("AROMA_ENV", "test")

    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

    # Monkeypatch everywhere it might be used
    monkeypatch.setattr(db.session, "AsyncSessionLocal", AsyncSessionLocal)
    monkeypatch.setattr(bot.services.drafts_store, "AsyncSessionLocal", AsyncSessionLocal)
    monkeypatch.setattr(bot.services.plans_store, "AsyncSessionLocal", AsyncSessionLocal)
    monkeypatch.setattr(bot.services.miniapp_references, "AsyncSessionLocal", AsyncSessionLocal)
    monkeypatch.setattr(bot.services.miniapp_references.common, "AsyncSessionLocal", AsyncSessionLocal)
    monkeypatch.setattr(bot.services.miniapp_references.aroma, "AsyncSessionLocal", AsyncSessionLocal)
    monkeypatch.setattr(bot.services.miniapp_references.blend, "AsyncSessionLocal", AsyncSessionLocal)
    monkeypatch.setattr(bot.services.miniapp_references.crystal, "AsyncSessionLocal", AsyncSessionLocal)
    monkeypatch.setattr(bot.services.miniapp_references.symptom, "AsyncSessionLocal", AsyncSessionLocal)
    monkeypatch.setattr(bot.services.draft_revisions_store, "AsyncSessionLocal", AsyncSessionLocal)
    monkeypatch.setattr(bot.services.kb_context_builder, "AsyncSessionLocal", AsyncSessionLocal)
    monkeypatch.setattr(bot.services.post_metrics_store, "AsyncSessionLocal", AsyncSessionLocal)
    monkeypatch.setattr(bot.services.daily_oil, "AsyncSessionLocal", AsyncSessionLocal)
    monkeypatch.setattr(analytics.trend_signal_store, "AsyncSessionLocal", AsyncSessionLocal)
    monkeypatch.setattr(analytics.signal_enricher, "AsyncSessionLocal", AsyncSessionLocal)
    monkeypatch.setattr(analytics.trend_intelligence, "AsyncSessionLocal", AsyncSessionLocal)
    monkeypatch.setattr(bot.services.llm_cache, "AsyncSessionLocal", AsyncSessionLocal)
    monkeypatch.setattr(bot.services.brand_settings_store, "AsyncSessionLocal", AsyncSessionLocal)
    monkeypatch.setattr(bot.services.subscription_store, "AsyncSessionLocal", AsyncSessionLocal)
    monkeypatch.setattr(bot.services.blends_store, "AsyncSessionLocal", AsyncSessionLocal)
    monkeypatch.setattr(bot.services.saved_blends_store, "AsyncSessionLocal", AsyncSessionLocal)
    monkeypatch.setattr(bot.services.mentions_store, "AsyncSessionLocal", AsyncSessionLocal)
    monkeypatch.setattr(bot.services.inbox_store, "AsyncSessionLocal", AsyncSessionLocal)
    monkeypatch.setattr(bot.services.cost_stats_store, "AsyncSessionLocal", AsyncSessionLocal)
    monkeypatch.setattr(bot.services.publish_log_store, "AsyncSessionLocal", AsyncSessionLocal)
    monkeypatch.setattr(bot.services.tracked_threads_store, "AsyncSessionLocal", AsyncSessionLocal)
    monkeypatch.setattr(bot.services.team_store, "AsyncSessionLocal", AsyncSessionLocal)
    monkeypatch.setattr(bot.services.video_task_store, "AsyncSessionLocal", AsyncSessionLocal)
    monkeypatch.setattr(bot.services.social_trends_store, "AsyncSessionLocal", AsyncSessionLocal)
    monkeypatch.setattr(bot.services.past_publications_store, "AsyncSessionLocal", AsyncSessionLocal)
    monkeypatch.setattr(bot.services.content_analytics, "AsyncSessionLocal", AsyncSessionLocal)
    monkeypatch.setattr(bot.services.analytics_store, "AsyncSessionLocal", AsyncSessionLocal)
    monkeypatch.setattr(bot.services.digest_store, "AsyncSessionLocal", AsyncSessionLocal)
    monkeypatch.setattr(miniapp.api.routers.plans, "AsyncSessionLocal", AsyncSessionLocal)
    monkeypatch.setattr(miniapp.api.routers.misc, "AsyncSessionLocal", AsyncSessionLocal)

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
