import os
import pytest
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from db.models import Base
import db.session
import bot.services.drafts_store
import bot.services.miniapp_references

# Use in-memory SQLite for tests
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

@pytest.fixture(autouse=True, scope="function")
async def setup_test_db(monkeypatch):
    # Re-create session factory for the test database
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    
    # Monkeypatch everywhere it might be used
    monkeypatch.setattr(db.session, "AsyncSessionLocal", AsyncSessionLocal)
    monkeypatch.setattr(bot.services.drafts_store, "AsyncSessionLocal", AsyncSessionLocal)
    monkeypatch.setattr(bot.services.miniapp_references, "AsyncSessionLocal", AsyncSessionLocal)
    
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield
    
    # Cleanup
    await engine.dispose()
