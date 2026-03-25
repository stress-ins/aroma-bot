"""Tests for Wellness Vertical Expansion: crystal therapy + enhanced sound healing."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from bot.services.miniapp_references import (
    get_reference_card,
    list_reference_cards,
    _seeded_payload,
)
from db.models import AromaCardModel
import bot.services.miniapp_references as _refs_module


ROOT = Path(__file__).resolve().parents[1]


# ── Helper ───────────────────────────────────────────────────────────────────

async def _insert_card(
    slug: str,
    name: str,
    category: str,
    source_type: str,
    payload: dict,
    aliases: list | None = None,
) -> None:
    """Insert a test card using the monkeypatched AsyncSessionLocal."""
    AsyncSessionLocal = _refs_module.AsyncSessionLocal
    async with AsyncSessionLocal() as session:
        session.add(
            AromaCardModel(
                slug=slug,
                name=name,
                category=category,
                source_type=source_type,
                aliases=aliases or [],
                payload=_seeded_payload(payload),
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()


# ── Seed data files exist and are valid JSON ─────────────────────────────────

def test_crystal_seed_file_exists():
    path = ROOT / "data" / "crystal_cards_seed.json"
    assert path.exists(), "data/crystal_cards_seed.json must exist"
    cards = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(cards, list)
    assert len(cards) >= 20, f"Expected at least 20 crystal cards, got {len(cards)}"


def test_sound_healing_seed_file_exists():
    path = ROOT / "data" / "sound_healing_seed.json"
    assert path.exists(), "data/sound_healing_seed.json must exist"
    cards = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(cards, list)
    assert len(cards) >= 10, f"Expected at least 10 sound healing cards, got {len(cards)}"


def test_crystal_seed_has_required_fields():
    path = ROOT / "data" / "crystal_cards_seed.json"
    cards = json.loads(path.read_text(encoding="utf-8"))
    required_slugs = {
        "clear-quartz", "rose-quartz", "amethyst", "citrine", "smoky-quartz",
        "black-tourmaline", "selenite", "labradorite", "moonstone", "tiger-eye",
        "lapis-lazuli", "jade", "obsidian", "carnelian", "fluorite",
        "malachite", "amazonite", "sodalite", "rhodonite", "hematite",
    }
    actual_slugs = {c["slug"] for c in cards}
    missing = required_slugs - actual_slugs
    assert not missing, f"Missing required crystal slugs: {missing}"

    for card in cards:
        assert card["category"] == "crystal", f"{card['slug']}: category must be 'crystal'"
        payload = card["payload"]
        assert payload.get("description"), f"{card['slug']}: missing description"
        assert payload.get("therapeutic_properties"), f"{card['slug']}: missing therapeutic_properties"
        assert payload.get("psychological_properties"), f"{card['slug']}: missing psychological_properties"
        assert payload.get("chakras"), f"{card['slug']}: missing chakras"
        assert payload.get("complementary_oils"), f"{card['slug']}: missing complementary_oils"
        assert payload.get("color"), f"{card['slug']}: missing color"
        assert payload.get("care_instructions"), f"{card['slug']}: missing care_instructions"


def test_sound_healing_seed_has_required_fields():
    path = ROOT / "data" / "sound_healing_seed.json"
    cards = json.loads(path.read_text(encoding="utf-8"))
    required_slugs = {
        "tibetan-singing-bowl", "crystal-singing-bowl", "gong-bath",
        "tuning-fork-therapy", "shamanic-drum", "binaural-beats",
        "sound-meditation", "voice-healing", "rain-stick", "ocean-drum",
    }
    actual_slugs = {c["slug"] for c in cards}
    missing = required_slugs - actual_slugs
    assert not missing, f"Missing required sound healing slugs: {missing}"

    for card in cards:
        assert card["category"] == "sound", f"{card['slug']}: category must be 'sound'"
        payload = card["payload"]
        assert payload.get("description"), f"{card['slug']}: missing description"
        assert payload.get("therapeutic_properties"), f"{card['slug']}: missing therapeutic_properties"
        assert payload.get("complementary_oils"), f"{card['slug']}: missing complementary_oils"
        assert payload.get("session_duration"), f"{card['slug']}: missing session_duration"


# ── Keywords registry ────────────────────────────────────────────────────────

def test_keywords_registry_has_crystal_therapy():
    from keywords.registry import TOPICS
    topic_names = [t.name for t in TOPICS]
    assert "Кристаллотерапия" in topic_names, "TOPICS must include crystal therapy topic"


def test_keywords_registry_has_sound_healing():
    from keywords.registry import TOPICS
    topic_names = [t.name for t in TOPICS]
    assert "Звукотерапия" in topic_names, "TOPICS must include sound healing topic"


def test_crystal_keywords_in_flat_lists():
    from keywords.registry import ALL_KEYWORDS
    assert "crystal healing" in ALL_KEYWORDS
    assert "кристаллотерапия" in ALL_KEYWORDS


def test_sound_keywords_in_flat_lists():
    from keywords.registry import ALL_KEYWORDS
    assert "sound healing" in ALL_KEYWORDS
    assert "звукотерапия" in ALL_KEYWORDS


# ── Wellness expert agent ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_wellness_expert_crystal_valid():
    from bot.agents.wellness_expert import verify_wellness_content
    card = {
        "name": "Аметист",
        "source_type": "quartz",
        "payload": {
            "therapeutic_properties": ["снятие головной боли", "улучшение сна"],
            "psychological_properties": ["интуиция", "духовный рост"],
            "chakras": ["аджна", "сахасрара"],
            "color": "фиолетовый",
            "crystal_system": "тригональная",
            "hardness": 7,
            "care_instructions": "Очистка под проточной водой",
            "contraindications": [],
        },
    }
    result = await verify_wellness_content(card, "crystal", dry_run=True)
    assert result["valid"] is True
    assert result["confidence"] >= 0.7


@pytest.mark.asyncio
async def test_wellness_expert_crystal_missing_fields():
    from bot.agents.wellness_expert import verify_wellness_content
    card = {
        "name": "Bad Crystal",
        "source_type": "unknown_type",
        "payload": {},
    }
    result = await verify_wellness_content(card, "crystal", dry_run=True)
    assert result["confidence"] < 0.7
    assert len(result["issues"]) > 0


@pytest.mark.asyncio
async def test_wellness_expert_sound_valid():
    from bot.agents.wellness_expert import verify_wellness_content
    card = {
        "name": "Гонг-баня",
        "source_type": "gong",
        "payload": {
            "therapeutic_properties": ["релаксация", "снятие стресса"],
            "frequency_range": "16-20000 Гц",
            "session_duration": "45-90 минут",
            "contraindications": ["эпилепсия"],
        },
    }
    result = await verify_wellness_content(card, "sound", dry_run=True)
    assert result["valid"] is True


@pytest.mark.asyncio
async def test_wellness_expert_unsupported_category():
    from bot.agents.wellness_expert import verify_wellness_content
    result = await verify_wellness_content({}, "unknown_category", dry_run=True)
    assert result["valid"] is False
    assert "unsupported category" in result["issues"][0]


# ── Reference card CRUD for crystal category ─────────────────────────────────

@pytest.mark.asyncio
async def test_crystal_category_in_reference_categories():
    from bot.services.miniapp_references.common import REFERENCE_CATEGORIES
    assert "crystal" in REFERENCE_CATEGORIES


@pytest.mark.asyncio
async def test_crystal_card_list():
    await _insert_card(
        "crystal-test-quartz", "Тест-кварц", "crystal", "quartz",
        {"description": "test", "color": "white"},
    )
    items = await list_reference_cards("crystal")
    assert len(items) == 1
    assert items[0]["slug"] == "crystal-test-quartz"
    assert items[0]["category"] == "crystal"


@pytest.mark.asyncio
async def test_crystal_card_detail_with_cross_refs():
    # Insert a crystal card with complementary oils
    await _insert_card(
        "crystal-amethyst", "Аметист", "crystal", "quartz",
        {
            "description": "Камень мудрости",
            "complementary_oils": ["Лаванда"],
            "chakras": ["аджна"],
            "color": "фиолетовый",
        },
    )
    # Insert an aroma card that the crystal references
    await _insert_card(
        "lavender", "Лаванда", "aroma", "flower",
        {"description": "Лаванда для спокойствия"},
    )
    card = await get_reference_card("crystal", "crystal-amethyst")
    assert card is not None
    assert card["slug"] == "crystal-amethyst"
    # Cross-reference: complementary oil slugs should be resolved
    assert "complementary_oil_slugs" in card
    assert "lavender" in card["complementary_oil_slugs"]


@pytest.mark.asyncio
async def test_sound_card_list():
    await _insert_card(
        "test-singing-bowl", "Тибетская чаша", "sound", "singing_bowl",
        {"description": "test sound card", "session_duration": "30 min"},
    )
    items = await list_reference_cards("sound")
    assert len(items) >= 1
    assert all(item["category"] == "sound" for item in items)
    assert any(item["slug"] == "test-singing-bowl" for item in items)


@pytest.mark.asyncio
async def test_crystal_not_in_aroma_list():
    """Crystal cards must not leak into aroma list."""
    await _insert_card("aroma-test", "Тест-аромат", "aroma", "herb", {})
    await _insert_card("crystal-test", "Тест-кристалл", "crystal", "quartz", {})
    aromas = await list_reference_cards("aroma")
    for item in aromas:
        assert item["category"] == "aroma"


# ── Seed script can be imported ──────────────────────────────────────────────

def test_seed_script_importable():
    from scripts.seed_crystals import seed_crystals, seed_sound_healing
    assert callable(seed_crystals)
    assert callable(seed_sound_healing)


# ── References API returns crystal category ──────────────────────────────────

@pytest.mark.asyncio
async def test_references_api_crystal_category(monkeypatch):
    """The references API should return crystal category items."""
    import os
    from httpx import AsyncClient, ASGITransport
    from miniapp_server import app

    monkeypatch.setenv("AROMA_BYPASS_AUTH", "1")
    monkeypatch.setenv("AROMA_ENV", "test")

    await _insert_card(
        "api-crystal", "API Кварц", "crystal", "quartz",
        {"description": "API test crystal"},
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/references/crystal")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert any(item["slug"] == "api-crystal" for item in data["items"])
