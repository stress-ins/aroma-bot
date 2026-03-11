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
            "payload": {"name": "Test Oil", "description": "Old description"},
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
        from sqlalchemy import select
        res = await session.execute(select(AromaCardModel).filter(AromaCardModel.slug == "test-oil"))
        model = res.scalar_one_or_none()
        assert model is not None
        assert model.name == "Test Oil"
        assert model.payload["description"] == "Old description"

    # 2. Update the data file
    test_data[0]["payload"]["description"] = "New description"
    data_file.write_text(json.dumps(test_data), encoding="utf-8")
    
    # 3. Run patch again (Update)
    await patch_main()
    
    async with SessionLocal() as session:
        res = await session.execute(select(AromaCardModel).filter(AromaCardModel.slug == "test-oil"))
        model = res.scalar_one_or_none()
        assert model is not None
        assert model.payload["description"] == "New description"
