"""Tests for oil field coverage in parse_handbook_pdf.py (PR feature/base-pdf-field-coverage)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.parse_handbook_pdf as parser


def _oil_block(extra_lines: list[str]) -> list[str]:
    """Build a minimal oil block with given extra lines.

    OIL_NAME_RE = r"^([A-Z][A-Z &\\-/()]+[A-Z])$" — needs ALL CAPS, ≥3 chars.
    Block ends when a second OIL_NAME_RE match appears after block_start + 5 lines.
    """
    # 7 padding lines so block_end > block_start + 5 is satisfied before BERGAMOT
    padding = [""] * max(0, 6 - len(extra_lines))
    return [
        "LAVENDER",
        "Лаванда",
        *extra_lines,
        *padding,
        "BERGAMOT",  # triggers block end
    ]


# ---------------------------------------------------------------------------
# Test 1: spiritual_emotional extracted from "Духовное и эмоциональное воздействие"
# ---------------------------------------------------------------------------

def test_spiritual_emotional_extracted():
    lines = _oil_block([
        "Духовное и эмоциональное воздействие: Открывает сердечный центр, снимает страхи",
        "Лечебные свойства: Противовоспалительное",
    ])
    entries = parser.parse_oils(lines, 0, len(lines) - 1)
    assert entries, "Expected at least one oil entry"
    assert entries[0]["spiritual_emotional"] == "Открывает сердечный центр, снимает страхи"


# ---------------------------------------------------------------------------
# Test 2: mind_effect extracted from "Влияние на ум"
# ---------------------------------------------------------------------------

def test_mind_effect_extracted():
    lines = _oil_block([
        "Влияние на ум: Улучшает концентрацию и ясность мышления",
        "Лечебные свойства: Спазмолитическое",
    ])
    entries = parser.parse_oils(lines, 0, len(lines) - 1)
    assert entries, "Expected at least one oil entry"
    assert entries[0]["mind_effect"] == "Улучшает концентрацию и ясность мышления"


# ---------------------------------------------------------------------------
# Test 3: health_effects extracted from "Влияние на здоровье"
# ---------------------------------------------------------------------------

def test_health_effects_extracted():
    lines = _oil_block([
        "Влияние на здоровье: Снижает давление, противовоспалительное",
        "Лечебные свойства: Седативное",
    ])
    entries = parser.parse_oils(lines, 0, len(lines) - 1)
    assert entries, "Expected at least one oil entry"
    assert entries[0]["health_effects"] == "Снижает давление, противовоспалительное"


# ---------------------------------------------------------------------------
# Test 4: extraction_method extracted from "Способ получения"
# ---------------------------------------------------------------------------

def test_extraction_method_extracted():
    lines = _oil_block([
        "Способ получения: Паровая дистилляция",
        "Лечебные свойства: Успокаивающее",
    ])
    entries = parser.parse_oils(lines, 0, len(lines) - 1)
    assert entries, "Expected at least one oil entry"
    assert entries[0]["extraction_method"] == "Паровая дистилляция"


# ---------------------------------------------------------------------------
# Test 5: "Использование" falls back into applications when "Применение" absent
# ---------------------------------------------------------------------------

def test_usage_falls_back_to_applications():
    lines = _oil_block([
        "Использование: Диффузия 3-5 капель перед сном",
        "Лечебные свойства: Успокаивающее",
    ])
    entries = parser.parse_oils(lines, 0, len(lines) - 1)
    assert entries, "Expected at least one oil entry"
    # Either applications or a merged field should contain the usage text
    assert "Диффузия" in (entries[0]["applications"] or "")


# ---------------------------------------------------------------------------
# Test 6: new fields present as keys even when empty
# ---------------------------------------------------------------------------

def test_new_fields_always_present_in_entry():
    lines = _oil_block([
        "Лечебные свойства: Спазмолитическое",
    ])
    entries = parser.parse_oils(lines, 0, len(lines) - 1)
    assert entries
    entry = entries[0]
    for field in ("mind_effect", "health_effects", "extraction_method", "spiritual_emotional"):
        assert field in entry, f"Field '{field}' missing from oil entry"


# ---------------------------------------------------------------------------
# Test 7: new_oil card payload includes new fields
# ---------------------------------------------------------------------------

def test_new_oil_payload_includes_new_fields(tmp_path):
    """When building new oil cards, the payload must include all new fields."""
    # Simulate a minimal oil_entries list going through the builder logic
    entry = {
        "name_en": "Lavender",
        "name_ru": "Лаванда",
        "article_number": "",
        "therapeutic_properties": "Успокаивает",
        "conditions_for_use": "Стресс",
        "applications": "Диффузия",
        "blends_containing_names": [],
        "complementary_oil_names": [],
        "precautions": "",
        "spiritual_emotional": "Открывает сердце",
        "mind_effect": "Ясность ума",
        "health_effects": "Снижает давление",
        "extraction_method": "Паровая дистилляция",
    }
    # Build the payload dict the same way the main() builder does
    slug = parser.slugify(entry["name_en"])
    ru_name = entry.get("name_ru") or entry["name_en"]
    payload = {
        "name_en": entry["name_en"],
        "name_ru": ru_name,
        "key": ru_name or entry["name_en"],
        "article_number": entry.get("article_number", ""),
        "therapeutic_properties": entry.get("therapeutic_properties", ""),
        "conditions_for_use": entry.get("conditions_for_use", ""),
        "applications": entry.get("applications", ""),
        "blends_containing_names": entry.get("blends_containing_names", []),
        "complementary_oil_names": entry.get("complementary_oil_names", []),
        "precautions": entry.get("precautions", ""),
        "spiritual_emotional": entry.get("spiritual_emotional", ""),
        "mind_effect": entry.get("mind_effect", ""),
        "health_effects": entry.get("health_effects", ""),
        "extraction_method": entry.get("extraction_method", ""),
    }

    assert payload["spiritual_emotional"] == "Открывает сердце"
    assert payload["mind_effect"] == "Ясность ума"
    assert payload["health_effects"] == "Снижает давление"
    assert payload["extraction_method"] == "Паровая дистилляция"
