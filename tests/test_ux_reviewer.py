"""Tests for UX Reviewer agent (bot/agents/ux_reviewer.py)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# Test 1: filled card scores >= 0.7
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ux_reviewer_scores_filled_card():
    """A well-populated card should score >= 0.7 with no issues."""
    from bot.agents.ux_reviewer import review_card_ux

    card = {
        "name": "Лаванда",
        "source_type": "flower",
        "description": "Лаванда дамасская — успокаивающее масло с широким спектром действия. " * 3,
        "description_short": "Лаванда — масло спокойствия и сна.",
        "applications": "Диффузия: 3-5 капель\nМассаж: 2% в базовом масле",
        "complementary_oil_slugs": ["bergamot", "chamomile"],
        "complementary_oil_names": ["Бергамот", "Ромашка"],
    }

    result = await review_card_ux(card)

    assert result["score"] >= 0.7, f"Expected score >= 0.7, got {result['score']}. Issues: {result['issues']}"
    assert isinstance(result["passed"], bool)
    assert isinstance(result["issues"], list)


# ---------------------------------------------------------------------------
# Test 2: empty card scores < 0.5 and has issues
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ux_reviewer_scores_empty_card():
    """A card with empty required fields should score < 0.5 and list issues."""
    from bot.agents.ux_reviewer import review_card_ux

    card = {
        "name": "",
        "source_type": "",
        "description": "Подробное описание масла.",
        "description_short": "",  # Missing when description present
        "applications": "",
        "complementary_oil_slugs": [],
        "complementary_oil_names": [],
    }

    result = await review_card_ux(card)

    assert result["score"] < 0.7, f"Expected score < 0.7 (failing threshold), got {result['score']}"
    assert len(result["issues"]) > 0, "Expected at least one issue for empty card"


# ---------------------------------------------------------------------------
# Test 3: description_short truncation artifact is flagged
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ux_reviewer_flags_truncated_description():
    """Cards with truncation artifacts in description_short should be flagged."""
    from bot.agents.ux_reviewer import review_card_ux

    card = {
        "name": "Ладан",
        "source_type": "resin",
        "description": "Ладан священный — смоляное масло с тысячелетней историей.",
        "description_short": '{"name": "Ладан", "therapeutic_properties": "очищение',
        "applications": "Диффузия",
    }

    result = await review_card_ux(card)

    # Should flag that description_short contains JSON artifact
    assert any("json" in i.lower() or "raw" in i.lower() for i in result["issues"]), (
        f"Expected JSON artifact issue, got: {result['issues']}"
    )


# ---------------------------------------------------------------------------
# Test 4: unknown source_type is flagged
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ux_reviewer_flags_unknown_source_type():
    """Cards with unrecognised source_type should have it flagged."""
    from bot.agents.ux_reviewer import review_card_ux

    card = {
        "name": "Неизвестное",
        "source_type": "unknown_category",
        "description": "Описание",
        "description_short": "Краткое",
        "applications": "Диффузия",
    }

    result = await review_card_ux(card)

    assert any("source_type" in i for i in result["issues"]), (
        f"Expected source_type issue, got: {result['issues']}"
    )


# ---------------------------------------------------------------------------
# Test 5: mismatched slug/name arrays are flagged
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ux_reviewer_flags_slug_name_mismatch():
    """Mismatched complementary_oil_slugs vs _names lengths should be flagged."""
    from bot.agents.ux_reviewer import review_card_ux

    card = {
        "name": "Бергамот",
        "source_type": "citrus",
        "description": "Описание бергамота.",
        "description_short": "Бергамот — цитрусовое масло.",
        "applications": "Диффузия",
        "complementary_oil_slugs": ["lavender", "frankincense"],
        "complementary_oil_names": ["Лаванда"],  # One name, two slugs
    }

    result = await review_card_ux(card)

    assert any("different lengths" in i or "length" in i.lower() for i in result["issues"]), (
        f"Expected length mismatch issue, got: {result['issues']}"
    )
