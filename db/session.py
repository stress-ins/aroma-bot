from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from pathlib import Path
from config import settings

# For now, default to SQLite for easy migration from drafts.json
DB_PATH = Path(__file__).parent.parent / "data" / "aroma.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def init_db():
    from db.models import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
