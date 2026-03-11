import json
import pytest
from sqlalchemy import text
from scripts.patch_aroma_cards import main as patch_main
import db.session
from db.session import AsyncSessionLocal
from db.models import Base, AromaCardModel

@pytest.mark.asyncio
async def test_patch_aroma_cards_upsert(monkeypatch, tmp_path):
    # Create a temporary data file for the test
    test_data = [
        {
            "slug": "test-oil",
            "name": "Test Oil",
            "source_type": "herb",
            "aliases": "[]",
            "payload": json.dumps({"name": "Test Oil", "description": "Old description"}),
            "category": "aroma"
        }
    ]
    data_file = tmp_path / "test_cards.json"
    data_file.write_text(json.dumps(test_data), encoding="utf-8")
    
    # Mock the CARDS_JSON path in the script
    import scripts.patch_aroma_cards
    monkeypatch.setattr(scripts.patch_aroma_cards, "CARDS_JSON", data_file)
    
    # Use a specific test database for this test to avoid sharing issues
    db_file = tmp_path / "patch_test.db"
    test_db_url = f"sqlite+aiosqlite:///{db_file}"
    
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    engine = create_async_engine(test_db_url, echo=False)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    
    # Monkeypatch the session local in both the module and the script
    monkeypatch.setattr(db.session, "AsyncSessionLocal", SessionLocal)
    monkeypatch.setattr(scripts.patch_aroma_cards, "AsyncSessionLocal", SessionLocal)
    
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # 1. Run patch (Initial insert)
    await patch_main()
    
    async with SessionLocal() as session:
        res = await session.execute(text("SELECT name, payload FROM aroma_cards WHERE slug='test-oil'"))
        row = res.fetchone()
        assert row is not None
        assert row[0] == "Test Oil"
        assert json.loads(row[1])["description"] == "Old description"

    # 2. Update the data file
    test_data[0]["payload"] = json.dumps({"name": "Test Oil", "description": "New description"})
    data_file.write_text(json.dumps(test_data), encoding="utf-8")
    
    # 3. Run patch again (Update)
    await patch_main()
    
    async with SessionLocal() as session:
        res = await session.execute(text("SELECT name, payload FROM aroma_cards WHERE slug='test-oil'"))
        row = res.fetchone()
        assert row is not None
        assert json.loads(row[1])["description"] == "New description"
