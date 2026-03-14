"""Tests for Aromatherapy Expert agent (bot/agents/aromatherapy_expert.py)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# Test 1: well-formed lavender card scores >= 0.75
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_expert_validates_lavender_card():
    """A correctly populated lavender card should pass verification with score >= 0.75."""
    from bot.agents.aromatherapy_expert import verify_card_content

    card = {
        "name": "Лаванда",
        "source_type": "flower",
        "description_short": "Успокаивающее масло для нервной системы и сна.",
        "therapeutic_properties": "Успокаивающее, антисептическое, противовоспалительное, спазмолитическое.",
        "applications": "Диффузия: 3-5 капель. Массаж: 2% в базовом масле. Ванна: 5-8 капель.",
        "precautions": "Первый триместр беременности — с осторожностью.",
        "complementary_oil_names": ["Бергамот", "Ромашка римская"],
    }

    result = await verify_card_content(card, dry_run=True)

    assert result["score"] >= 0.75, f"Expected score >= 0.75, got {result['score']}. Issues: {result['issues']}"


# ---------------------------------------------------------------------------
# Test 2: wrong source_type is flagged
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_expert_flags_wrong_source_type():
    """A card with a completely unknown source_type should be flagged by rule-based checks."""
    from bot.agents.aromatherapy_expert import verify_card_content

    # Card with a non-standard source_type value
    card = {
        "name": "Эвкалипт",
        "source_type": "unknown_plant_type",  # Not in the known set
        "description_short": "Масло эвкалипта.",
        "therapeutic_properties": "Противовирусное, антисептическое.",
        "applications": "Диффузия, ингаляция.",
    }

    result = await verify_card_content(card, dry_run=True)

    assert any("source_type" in i for i in result["issues"]), (
        f"Expected source_type issue for unknown type. Issues: {result['issues']}"
    )
    assert result["score"] < 1.0


# ---------------------------------------------------------------------------
# Test 3: correct symptom hierarchy passes
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_expert_validates_symptom_hierarchy():
    """A symptom with proper anatomical parent_group should pass verification."""
    from bot.agents.aromatherapy_expert import verify_card_content

    card = {
        "name": "Головная боль",
        "category": "symptom",
        "parent_group": "НЕРВНАЯ СИСТЕМА",
        "category_group": "БОЛЬ И ВОСПАЛЕНИЕ",
        "source_type": "symptom",
        "description_short": "Головная боль различной этиологии.",
        "applications": "Эфирное масло мяты: точечно на виски.",
    }

    result = await verify_card_content(card, dry_run=True)

    assert result["score"] >= 0.7, (
        f"Expected score >= 0.7 for proper symptom hierarchy. Got {result['score']}. Issues: {result['issues']}"
    )
    assert result["passed"] is True


# ---------------------------------------------------------------------------
# Test 4: disease name as parent_group is flagged
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_expert_flags_disease_as_parent_group():
    """A symptom with a disease name (not anatomical system) as parent_group should be flagged."""
    from bot.agents.aromatherapy_expert import verify_card_content

    card = {
        "name": "Диабетическая нейропатия",
        "category": "symptom",
        "parent_group": "РАК ГРУДИ",  # A disease, not an anatomical system
        "category_group": "МЕТАБОЛИЧЕСКИЕ НАРУШЕНИЯ",
        "source_type": "symptom",
    }

    result = await verify_card_content(card, dry_run=True)

    # Should flag parent_group as disease, not anatomical system
    assert any("parent_group" in i or "anatomical" in i.lower() for i in result["issues"]), (
        f"Expected parent_group issue. Issues: {result['issues']}"
    )


# ---------------------------------------------------------------------------
# Test 5: dry_run flag prevents API calls
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_expert_dry_run_no_api_call():
    """dry_run=True must not make any external API calls."""
    from bot.agents.aromatherapy_expert import verify_card_content
    from unittest.mock import patch

    card = {"name": "Эвкалипт", "source_type": "tree"}

    # Patch anthropic to detect if it gets called
    with patch("anthropic.Anthropic") as mock_anthropic:
        await verify_card_content(card, dry_run=True)
        mock_anthropic.assert_not_called()
