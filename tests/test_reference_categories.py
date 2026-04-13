"""Tests: symptoms stay in symptom category; blends use Russian names; symptom badge."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from bot.services.miniapp_references import list_reference_cards, get_reference_card
from db.models import AromaCardModel
import bot.services.miniapp_references as _refs_module


async def _insert_card(slug: str, name: str, category: str, source_type: str, payload: dict) -> None:
    """Insert a test card using the monkeypatched AsyncSessionLocal."""
    from bot.services.miniapp_references import _seeded_payload
    # Access AsyncSessionLocal via the module so monkeypatching in conftest applies
    AsyncSessionLocal = _refs_module.AsyncSessionLocal
    async with AsyncSessionLocal() as session:
        session.add(AromaCardModel(
            slug=slug,
            name=name,
            category=category,
            source_type=source_type,
            aliases=[],
            payload=_seeded_payload(payload),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ))
        await session.commit()


@pytest.mark.asyncio
async def test_symptom_items_not_in_aroma_list():
    """Items in aroma list must all have category='aroma'."""
    await _insert_card("aroma-lavender", "Лаванда", "aroma", "flower", {"category": "aroma"})
    await _insert_card("symptom-headache", "ГОЛОВНАЯ БОЛЬ", "symptom", "symptom", {"category": "symptom"})
    aromas = await list_reference_cards("aroma")
    for item in aromas:
        assert item["category"] == "aroma", (
            f"Non-aroma item in aroma list: slug={item['slug']}, category={item['category']}"
        )


@pytest.mark.asyncio
async def test_symptom_list_has_only_symptoms():
    """All items from list_reference_cards('symptom') must have category='symptom'."""
    await _insert_card("aroma-rose", "Роза", "aroma", "flower", {"category": "aroma"})
    await _insert_card("symptom-insomnia", "БЕССОННИЦА", "symptom", "symptom", {"category": "symptom"})
    symptoms = await list_reference_cards("symptom")
    for item in symptoms:
        assert item["category"] == "symptom", (
            f"Non-symptom item in symptom list: slug={item['slug']}, category={item['category']}"
        )


@pytest.mark.asyncio
async def test_blend_name_ru_is_primary():
    """Blend list items must use Russian name as primary when name_ru exists in payload."""
    await _insert_card(
        "blend-abundance", "Abundance", "blend", "blend",
        {"category": "blend", "name_ru": "Изобилие"},
    )
    blends = await list_reference_cards("blend")
    abundance = next((b for b in blends if b["slug"] == "blend-abundance"), None)
    assert abundance is not None, "blend-abundance not found in list"
    assert abundance["name"] == "Изобилие", f"Expected Russian name, got '{abundance['name']}'"
    assert abundance["name_en"] == "Abundance", f"Expected name_en='Abundance', got '{abundance.get('name_en')}'"


@pytest.mark.asyncio
async def test_blend_detail_name_ru_is_primary():
    """get_reference_card for blend must return Russian name as primary."""
    await _insert_card(
        "blend-acceptance", "Acceptance", "blend", "blend",
        {"category": "blend", "name_ru": "Принятие"},
    )
    card = await get_reference_card("blend", "blend-acceptance")
    assert card is not None
    assert card["name"] == "Принятие"
    assert card["name_en"] == "Acceptance"


@pytest.mark.asyncio
async def test_blend_without_name_ru_keeps_english_name():
    """Blend without name_ru has name_en='' and keeps original name."""
    await _insert_card(
        "blend-no-ru", "Harmony", "blend", "blend",
        {"category": "blend"},
    )
    blends = await list_reference_cards("blend")
    item = next((b for b in blends if b["slug"] == "blend-no-ru"), None)
    assert item is not None
    assert item["name"] == "Harmony"
    assert item["name_en"] == ""


@pytest.mark.asyncio
async def test_symptom_list_includes_parent_group():
    """Symptom list items include parent_group field for badge/filter."""
    await _insert_card(
        "symptom-anemia", "АНЕМИЯ", "symptom", "symptom",
        {"category": "symptom", "parent_group": "КРОВЕНОСНАЯ СИСТЕМА", "category_group": "ПАНКРЕАТИТ"},
    )
    symptoms = await list_reference_cards("symptom")
    item = next((s for s in symptoms if s["slug"] == "symptom-anemia"), None)
    assert item is not None
    assert item["parent_group"] == "КРОВЕНОСНАЯ СИСТЕМА"


@pytest.mark.asyncio
async def test_massage_items_stay_in_massage_list():
    """Items from list_reference_cards('massage') must all have category='massage'."""
    await _insert_card("massage-aroma", "Аромамассаж", "massage", "technique", {"category": "massage"})
    await _insert_card("aroma-lavender2", "Лаванда2", "aroma", "flower", {"category": "aroma"})
    cards = await list_reference_cards("massage")
    for item in cards:
        assert item["category"] == "massage", (
            f"Non-massage item in massage list: slug={item['slug']}, category={item['category']}"
        )


@pytest.mark.asyncio
async def test_osteo_items_stay_in_osteo_list():
    """Items from list_reference_cards('osteo') must all have category='osteo'."""
    await _insert_card("osteo-cranio", "Краниосакральная техника", "osteo", "technique", {"category": "osteo"})
    cards = await list_reference_cards("osteo")
    for item in cards:
        assert item["category"] == "osteo"


@pytest.mark.asyncio
async def test_biodynamics_items_stay_in_biodynamics_list():
    """Items from list_reference_cards('biodynamics') must all have category='biodynamics'."""
    await _insert_card("bio-primary", "Первичное дыхание", "biodynamics", "principle", {"category": "biodynamics"})
    cards = await list_reference_cards("biodynamics")
    for item in cards:
        assert item["category"] == "biodynamics"


@pytest.mark.asyncio
async def test_massage_detail_returns_card():
    """get_reference_card for massage must return the correct card."""
    await _insert_card(
        "massage-lymph", "Лимфодренажный массаж", "massage", "technique",
        {"category": "massage", "name_en": "Lymphatic Drainage", "description_short": "Мягкий массаж"},
    )
    card = await get_reference_card("massage", "massage-lymph")
    assert card is not None
    assert card["slug"] == "massage-lymph"
    assert card["description_short"] == "Мягкий массаж"


@pytest.mark.asyncio
async def test_reference_categories_include_bodywork():
    """REFERENCE_CATEGORIES must include massage, osteo, biodynamics."""
    from bot.services.miniapp_references.common import REFERENCE_CATEGORIES
    for cat in ("massage", "osteo", "biodynamics"):
        assert cat in REFERENCE_CATEGORIES, f"{cat} missing from REFERENCE_CATEGORIES"
