import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from pathlib import Path
from typing import AsyncGenerator

# Default SQLite database path
_DEFAULT_DB_PATH = Path(__file__).parent.parent / "data" / "aroma.db"
_DEFAULT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

def get_database_url() -> str:
    return os.getenv("AROMA_DATABASE_URL", f"sqlite+aiosqlite:///{_DEFAULT_DB_PATH}")


DATABASE_URL = get_database_url()

def create_session_factory(url: str | None = None):
    engine = create_async_engine(url or DATABASE_URL, echo=False)
    return async_sessionmaker(engine, expire_on_commit=False)

# Global session factory that can be used directly or replaced in tests
AsyncSessionLocal = create_session_factory()

async def init_db():
    from db.models import Base
    engine = create_async_engine(DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
