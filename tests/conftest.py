import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool
from db.models import Base
import db.session
import bot.services.drafts_store
import bot.services.plans_store
import bot.services.miniapp_references
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
import bot.services.cost_stats_store
import bot.services.publish_log_store
import bot.services.tracked_threads_store
import miniapp.api.routers.plans
import miniapp.api.routers.misc


@pytest.fixture(autouse=True, scope="function")
async def setup_test_db(monkeypatch):
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
    monkeypatch.setattr(bot.services.cost_stats_store, "AsyncSessionLocal", AsyncSessionLocal)
    monkeypatch.setattr(bot.services.publish_log_store, "AsyncSessionLocal", AsyncSessionLocal)
    monkeypatch.setattr(bot.services.tracked_threads_store, "AsyncSessionLocal", AsyncSessionLocal)
    monkeypatch.setattr(miniapp.api.routers.plans, "AsyncSessionLocal", AsyncSessionLocal)
    monkeypatch.setattr(miniapp.api.routers.misc, "AsyncSessionLocal", AsyncSessionLocal)

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Preload brand settings cache so sync callers don't crash
    from bot.services.brand_settings_store import preload_brand_settings
    await preload_brand_settings()

    yield

    # Cleanup
    await engine.dispose()
