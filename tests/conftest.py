import os
import pytest
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from db.models import Base, DraftModel, AromaCardModel
import db.session
import bot.services.drafts_store
import bot.services.miniapp_references
import scripts.patch_aroma_cards

@pytest.fixture(autouse=True, scope="function")
async def setup_test_db(monkeypatch, tmp_path):
    # Use a temporary file-based SQLite for tests to ensure connection sharing works
    db_file = tmp_path / "test_aroma.db"
    test_db_url = f"sqlite+aiosqlite:///{db_file}"
    
    # Re-create session factory for the test database
    engine = create_async_engine(test_db_url, echo=False)
    AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    
    # Monkeypatch everywhere it might be used
    monkeypatch.setattr(db.session, "AsyncSessionLocal", AsyncSessionLocal)
    monkeypatch.setattr(bot.services.drafts_store, "AsyncSessionLocal", AsyncSessionLocal)
    monkeypatch.setattr(bot.services.miniapp_references, "AsyncSessionLocal", AsyncSessionLocal)
    monkeypatch.setattr(scripts.patch_aroma_cards, "AsyncSessionLocal", AsyncSessionLocal)
    
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield
    
    # Cleanup
    await engine.dispose()
