import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from pathlib import Path
from config import settings

# Default SQLite database path
_DEFAULT_DB_PATH = Path(__file__).parent.parent / "data" / "aroma.db"
_DEFAULT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# Allow override via environment variable
DATABASE_URL = os.getenv("AROMA_DATABASE_URL", f"sqlite+aiosqlite:///{_DEFAULT_DB_PATH}")

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def init_db():
    from db.models import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
