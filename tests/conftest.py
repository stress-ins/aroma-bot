import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from db.models import Base
import db.session
import bot.services.drafts_store
import bot.services.plans_store
import bot.services.miniapp_references

@pytest.fixture(autouse=True, scope="function")
async def setup_test_db(monkeypatch, tmp_path):
    test_database_url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    # Re-create session factory for the test database
    engine = create_async_engine(test_database_url, echo=False)
    AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    
    # Monkeypatch everywhere it might be used
    monkeypatch.setattr(db.session, "AsyncSessionLocal", AsyncSessionLocal)
    monkeypatch.setattr(bot.services.drafts_store, "AsyncSessionLocal", AsyncSessionLocal)
    monkeypatch.setattr(bot.services.plans_store, "AsyncSessionLocal", AsyncSessionLocal)
    monkeypatch.setattr(bot.services.miniapp_references, "AsyncSessionLocal", AsyncSessionLocal)
    
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield
    
    # Cleanup
    await engine.dispose()
