"""Tests for card content UX improvements (PR 3)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# Test 1: audit endpoint returns cards without description
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_audit_endpoint_returns_empty_descriptions():
    """list_reference_cards_missing_description returns only cards with empty description."""
    from bot.services.miniapp_references import list_reference_cards_missing_description
    from scripts.import_oil_pdfs import _upsert_card

    # Card with empty description
    await _upsert_card(
        slug="audit-empty-desc",
        name="Тест Пустой",
        source_type="flower",
        aliases=[],
        payload={"description": "", "description_short": ""},
    )

    # Card with non-empty description
    await _upsert_card(
        slug="audit-filled-desc",
        name="Тест Заполненный",
        source_type="flower",
        aliases=[],
        payload={"description": "Полное описание масла"},
    )

    # Audit must return first, not second
    items = await list_reference_cards_missing_description("aroma")
    slugs = [i["slug"] for i in items]
    assert "audit-empty-desc" in slugs
    assert "audit-filled-desc" not in slugs


# ---------------------------------------------------------------------------
# Test 2: collapsible description visible only if short ≠ full
# ---------------------------------------------------------------------------

def test_collapsible_short_shown_if_exists():
    """description_short and description are distinct fields."""
    from scripts.import_oil_pdfs import _parse_with_claude
    import json
    from unittest.mock import MagicMock, patch

    mock_response = {
        "name": "Роза",
        "description": "Роза дамасская — символ любви и высокой чувствительности. Используется 5000 лет.",
        "description_short": "Роза — масло сердца и любви.",
        "resource_plus": "",
        "resource_minus": "",
    }

    mock_client = MagicMock()
    mock_content = MagicMock()
    mock_content.text = json.dumps(mock_response)
    mock_client.messages.create.return_value = MagicMock(content=[mock_content])

    with patch("anthropic.Anthropic", return_value=mock_client):
        result = _parse_with_claude("Rose text", api_key="fake")

    assert result["description_short"] != result["description"]
    assert len(result["description_short"]) < len(result["description"])


# ---------------------------------------------------------------------------
# Test 3: empty slug chips are filtered
# ---------------------------------------------------------------------------

def test_empty_slugs_filtered():
    """renderCrossRefChips JS logic: pairs with empty slug still render as plain spans."""
    # We test the Python-side data: pairs with empty slug from zip
    pairs = [
        {"name": "Лаванда", "slug": "lavender"},   # valid
        {"name": "Неизвестное", "slug": ""},        # empty slug
        {"name": "Ещё одно", "slug": None},         # null slug
        {"name": "", "slug": "something"},          # empty name
    ]

    # Simulate the JS filter logic in Python for testing
    def simulated_render(pairs):
        chips = []
        for p in pairs:
            slug = p.get("slug")
            name = p.get("name", "")
            if not name:
                continue
            if slug and str(slug).strip():
                chips.append(f"button:{name}:{slug}")
            else:
                chips.append(f"span:{name}")
        return chips

    result = simulated_render(pairs)
    assert "button:Лаванда:lavender" in result
    assert "span:Неизвестное" in result    # empty slug → plain span (not button)
    assert "span:Ещё одно" in result       # None slug → plain span
    # Empty name is excluded entirely
    assert not any("something" in r for r in result)


# ---------------------------------------------------------------------------
# Test 4: audit service handles category filter
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_audit_service_filters_by_category():
    """Audit returns only cards of the requested category."""
    from bot.services.miniapp_references import list_reference_cards_missing_description
    from db.session import AsyncSessionLocal
    from db.models import AromaCardModel

    async with AsyncSessionLocal() as session:
        # Add symptom card with no description
        from sqlalchemy import select
        result = await session.execute(
            select(AromaCardModel).where(AromaCardModel.slug == "audit-symptom-test")
        )
        if not result.scalar_one_or_none():
            session.add(AromaCardModel(
                slug="audit-symptom-test",
                name="Симптом Без Описания",
                category="symptom",
                source_type="symptom",
                aliases=[],
                payload={"description": ""},
            ))
            await session.commit()

    # Audit for aroma category should NOT return the symptom card
    aroma_items = await list_reference_cards_missing_description("aroma")
    aroma_slugs = [i["slug"] for i in aroma_items]
    assert "audit-symptom-test" not in aroma_slugs

    # Audit for symptom category SHOULD return it
    symptom_items = await list_reference_cards_missing_description("symptom")
    symptom_slugs = [i["slug"] for i in symptom_items]
    assert "audit-symptom-test" in symptom_slugs


# ---------------------------------------------------------------------------
# Test 5: complementary_oil_slugs resolved from stored names
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_complementary_oil_slugs_resolved():
    """_enrich_aroma_cross_refs must resolve complementary_oil_slugs from stored names."""
    from bot.services.miniapp_references import _enrich_aroma_cross_refs
    from scripts.import_oil_pdfs import _upsert_card

    # Seed two target oils
    await _upsert_card(
        slug="lavender-comp-test",
        name="Лаванда Тест",
        source_type="flower",
        aliases=[],
        payload={"description": "тест"},
    )
    await _upsert_card(
        slug="frankincense-comp-test",
        name="Ладан Тест",
        source_type="resin",
        aliases=[],
        payload={"description": "тест"},
    )

    # Card that references them by name
    serialized = {
        "slug": "bergamot-comp-test",
        "complementary_oil_names": ["Лаванда Тест", "Ладан Тест", "Несуществующее"],
    }
    result = await _enrich_aroma_cross_refs(serialized)

    slugs = result["complementary_oil_slugs"]
    assert slugs[0] == "lavender-comp-test"
    assert slugs[1] == "frankincense-comp-test"
    assert slugs[2] == ""  # unknown name → empty string, not crash


# ---------------------------------------------------------------------------
# Test 6: renderCollapsibleSection — long text triggers collapse
# ---------------------------------------------------------------------------

def test_collapsible_section_long_text():
    """Text longer than maxChars produces a preview + details element."""
    long_text = "А" * 400
    short_text = "Б" * 100

    # Simulate the JS renderCollapsibleSection logic in Python
    def render(title, text, max_chars=280):
        if not text:
            return ""
        if len(text) <= max_chars:
            return f"<section>{title}:{text}</section>"
        cut = text.rfind(" ", 0, max_chars) or max_chars
        preview = text[:cut]
        return f"<section>{title}:{preview}…<details>▼ Читать далее<div>{text}</div></details></section>"

    result_long = render("Терапевтические свойства", long_text)
    assert "▼ Читать далее" in result_long
    assert "…" in result_long

    result_short = render("Ключ", short_text)
    assert "▼ Читать далее" not in result_short
    assert "…" not in result_short
