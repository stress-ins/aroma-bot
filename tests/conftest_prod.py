"""Shared fixtures for production database tests.

Usage: tests that need prod data should import the `prod_db` fixture.
The prod dump is at data/aroma_prod_dump.db — refresh with:
    scp root@46.32.186.192:/opt/aroma/data/aroma.db data/aroma_prod_dump.db
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from db.models import Base
import db.session
import bot.services.drafts_store
import bot.services.plans_store
import bot.services.miniapp_references
import bot.services.miniapp_references.common
import bot.services.miniapp_references.aroma
import bot.services.miniapp_references.blend
import bot.services.miniapp_references.symptom
import bot.services.draft_revisions_store
import bot.services.kb_context_builder

PROD_DUMP = Path(__file__).parent.parent / "data" / "aroma_prod_dump.db"


@pytest.fixture()
async def prod_db(monkeypatch, tmp_path):
    """Provide a read-only copy of the production database for testing.

    Copies the dump to tmp_path so the original is never modified.
    Skips the test if the dump file doesn't exist.
    """
    if not PROD_DUMP.exists():
        pytest.skip("Production dump not found: data/aroma_prod_dump.db")

    db_path = tmp_path / "prod_copy.db"
    shutil.copy2(PROD_DUMP, db_path)

    # Migrate the prod copy to current schema (add missing columns/tables)
    sync_engine = create_engine(f"sqlite:///{db_path}")
    # First create any entirely new tables
    Base.metadata.create_all(sync_engine)
    # Then add missing columns to existing tables
    with sync_engine.connect() as conn:
        for table in Base.metadata.sorted_tables:
            try:
                existing = {r[1] for r in conn.execute(text(f"PRAGMA table_info('{table.name}')")).fetchall()}
            except Exception:
                continue
            for col in table.columns:
                if col.name not in existing:
                    col_type = col.type.compile(dialect=sync_engine.dialect)
                    try:
                        conn.execute(text(f"ALTER TABLE {table.name} ADD COLUMN {col.name} {col_type}"))
                    except Exception:
                        pass
        conn.commit()
    sync_engine.dispose()

    url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_async_engine(url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    monkeypatch.setattr(db.session, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(bot.services.drafts_store, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(bot.services.plans_store, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(bot.services.miniapp_references, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(bot.services.miniapp_references.common, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(bot.services.miniapp_references.aroma, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(bot.services.miniapp_references.blend, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(bot.services.miniapp_references.symptom, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(bot.services.draft_revisions_store, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(bot.services.kb_context_builder, "AsyncSessionLocal", session_factory)

    yield db_path

    await engine.dispose()
