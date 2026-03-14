"""Tests for card content fixes: ingredient cleanup, symptom oil resolution, cross-refs."""
from __future__ import annotations

import re
from datetime import datetime, timezone

import pytest

import bot.services.miniapp_references as _refs_module
from bot.services.miniapp_references import (
    _extract_ru_name,
    _resolve_symptom_refs,
    get_reference_card,
)
from db.models import AromaCardModel


async def _insert(slug: str, name: str, category: str, source_type: str, payload: dict) -> None:
    from bot.services.miniapp_references import _seeded_payload
    AsyncSessionLocal = _refs_module.AsyncSessionLocal
    async with AsyncSessionLocal() as session:
        session.add(AromaCardModel(
            slug=slug, name=name, category=category, source_type=source_type,
            aliases=[], payload=_seeded_payload(payload),
            created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
        ))
        await session.commit()


# ── _extract_ru_name ──────────────────────────────────────────────────────────

def test_extract_ru_name_with_parens():
    assert _extract_ru_name("Fennel (Фенхель)") == "Фенхель"


def test_extract_ru_name_no_parens_returns_clean():
    assert _extract_ru_name("Peppermint") == "Peppermint"


def test_extract_ru_name_strips_sentence_continuation():
    raw = "Fennel (Фенхель) Подходит для создания. Распыляйте"
    assert _extract_ru_name(raw) == "Фенхель"


def test_extract_ru_name_normalizes_double_spaces():
    assert _extract_ru_name("Peppermint  (Мята  перечная)") == "Мята перечная"


# ── ingredient_names_ru extraction ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_blend_ingredient_names_ru_extracted():
    """Blend card must expose ingredient_names_ru with Russian names from parens."""
    await _insert("blend-test-ru", "TestBlend", "blend", "blend", {
        "category": "blend",
        "ingredient_names": [
            "Fennel (Фенхель)",
            "Peppermint (Мята перечная)",
            "Подходит для создания успокаивающей атмосферы. Распыляйте его дома",
            "в офисе и даже в автомобиле",
        ],
        "ingredient_slugs": ["fennel", "peppermint", "", ""],
    })
    card = await get_reference_card("blend", "blend-test-ru")
    assert card is not None
    ru_names = card.get("ingredient_names_ru", [])
    assert "Фенхель" in ru_names
    assert "Мята перечная" in ru_names
    # Long garbage strings must be filtered
    assert not any(len(n) > 60 for n in ru_names)


@pytest.mark.asyncio
async def test_blend_ingredient_no_sentence_continuation():
    """Ingredient names with sentence continuation ('. Capital') must be excluded."""
    await _insert("blend-test-filter", "FilterBlend", "blend", "blend", {
        "category": "blend",
        "ingredient_names": [
            "Fennel (Фенхель) Подходит для создания успокаивающей атмосферы. Распыляйте дома",
            "Lavender (Лаванда)",
        ],
        "ingredient_slugs": ["fennel", "lavender"],
    })
    card = await get_reference_card("blend", "blend-test-filter")
    ru_names = card.get("ingredient_names_ru", [])
    # Only Lavender should survive (Fennel has sentence continuation text)
    assert "Лаванда" in ru_names
    assert "Фенхель" not in ru_names


# ── _resolve_symptom_refs ────────────────────────────────────────────────────

def test_resolve_symptom_refs_filters_stop_words():
    name_to_slug = {"рекомендации": ""}
    slug_to_ru = {}
    names, slugs = _resolve_symptom_refs(
        ["РЕКОМЕНДАЦИИ", "Lavender", "Смеси"],
        name_to_slug, slug_to_ru
    )
    assert "РЕКОМЕНДАЦИИ" not in names
    assert "Смеси" not in names
    assert "Lavender" in names


def test_resolve_symptom_refs_filters_long_artifacts():
    name_to_slug = {}
    slug_to_ru = {}
    names, slugs = _resolve_symptom_refs(
        ["A" * 61, "Short"],
        name_to_slug, slug_to_ru
    )
    assert len(names) == 1
    assert names[0] == "Short"


def test_resolve_symptom_refs_filters_bullet_items():
    name_to_slug = {}
    slug_to_ru = {}
    names, slugs = _resolve_symptom_refs(
        ["• нанести на затылок", "Lavender"],
        name_to_slug, slug_to_ru
    )
    assert "• нанести на затылок" not in names
    assert "Lavender" in names


# ── Symptom cross-refs via get_reference_card ─────────────────────────────────

@pytest.mark.asyncio
async def test_symptom_recommended_oil_names_resolved():
    """Symptom card should resolve oil names to Russian via stored slugs."""
    # Add an aroma card with Russian name
    await _insert("lavender", "Лаванда", "aroma", "flower", {})
    # Add a symptom referencing it
    await _insert("symptom-stress", "СТРЕСС", "symptom", "symptom", {
        "recommended_oil_names": ["Lavender", "РЕКОМЕНДАЦИИ"],
        "recommended_oil_slugs": ["lavender", ""],
        "recommended_blend_names": [],
        "recommended_blend_slugs": [],
    })
    card = await get_reference_card("symptom", "symptom-stress")
    assert card is not None
    oil_names = card.get("recommended_oil_names", [])
    # "РЕКОМЕНДАЦИИ" must be filtered
    assert "РЕКОМЕНДАЦИИ" not in oil_names
    # Lavender slug resolves to Russian name from aroma DB
    assert "Лаванда" in oil_names


@pytest.mark.asyncio
async def test_symptom_recommended_oils_no_duplicate_slugs():
    """Duplicate slugs in symptom oil list must be deduplicated."""
    await _insert("frankincense", "Ладан", "aroma", "resin", {})
    await _insert("symptom-dup", "ДУБЛЬ", "symptom", "symptom", {
        "recommended_oil_names": ["Frankincense", "Sacred Frankincense"],
        "recommended_oil_slugs": ["frankincense", "frankincense"],
    })
    card = await get_reference_card("symptom", "symptom-dup")
    slugs = card.get("recommended_oil_slugs", [])
    # Should have at most one "frankincense" slug
    assert slugs.count("frankincense") <= 1


# ── Aroma → related symptoms cross-ref ────────────────────────────────────────

@pytest.mark.asyncio
async def test_aroma_card_has_related_symptom_names():
    """Aroma card must list symptoms that recommend it."""
    await _insert("lemon", "Лимон", "aroma", "citrus", {})
    await _insert("symptom-nausea", "ТОШНОТА", "symptom", "symptom", {
        "recommended_oil_names": ["Lemon"],
        "recommended_oil_slugs": ["lemon"],
    })
    card = await get_reference_card("aroma", "lemon")
    assert card is not None
    related = card.get("related_symptom_names", [])
    assert "ТОШНОТА" in related


@pytest.mark.asyncio
async def test_aroma_card_related_symptoms_empty_when_no_match():
    """Aroma with no symptom references must return empty related_symptom_names."""
    await _insert("sandalwood", "Сандал", "aroma", "tree", {})
    card = await get_reference_card("aroma", "sandalwood")
    assert card is not None
    assert card.get("related_symptom_names", []) == []
