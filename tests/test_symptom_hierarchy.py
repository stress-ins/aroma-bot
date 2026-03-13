"""Tests for symptom parent_group / 2-level hierarchy (PR 2)."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.parse_handbook_pdf as parser


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_lines(entries: list[tuple[str, str]]) -> list[str]:
    """Build a fake list of lines from (indent, text) pairs."""
    return [indent + text for indent, text in entries]


# ---------------------------------------------------------------------------
# Test 1: CAPS without indent → parent_group; CAPS with indent → category_group
# ---------------------------------------------------------------------------

def test_parent_group_detected_by_indentation():
    """parse_symptoms tracks parent_group (no-indent CAPS) vs category_group (indented CAPS)."""
    lines = [
        "",  # sym_start = 0, start from line 0
        "НЕРВНАЯ СИСТЕМА",           # no indent → parent_group
        "  ТРЕВОЖНЫЕ РАССТРОЙСТВА",  # indent → category_group
        "Паническая атака",          # symptom candidate
        "Одинарные: Лаванда",        # has recs
        "",
        "  ДЕПРЕССИВНЫЕ СОСТОЯНИЯ",  # indent → category_group
        "Апатия",
        "Одинарные: Ладан",
        "",
    ]

    entries = parser.parse_symptoms(lines, sym_start=0)

    assert len(entries) >= 1
    first = entries[0]
    assert first["payload"]["parent_group"] == "НЕРВНАЯ СИСТЕМА"
    assert first["payload"]["category_group"] == "ТРЕВОЖНЫЕ РАССТРОЙСТВА"


def test_parent_group_stored_in_payload():
    """Each symptom entry must have parent_group in payload."""
    lines = [
        "АЛЛЕРГИЯ",
        "Аллергический ринит",
        "Одинарные: Эвкалипт, Мята перечная",
        "",
    ]
    entries = parser.parse_symptoms(lines, sym_start=0)

    assert len(entries) >= 1
    for entry in entries:
        assert "parent_group" in entry["payload"]


def test_parent_group_empty_if_no_top_level_header():
    """If no top-level header seen, parent_group is empty string, category_group is set."""
    lines = [
        "  ЖЕНСКОЕ ЗДОРОВЬЕ",    # indented CAPS → category_group only, no parent_group change
        "Мастит",
        "Одинарные: Лаванда, Герань",
        "",
    ]
    entries = parser.parse_symptoms(lines, sym_start=0)

    if entries:
        # parent_group stays empty (default "")
        assert entries[0]["payload"]["parent_group"] == ""
        # category_group updated to the indented CAPS header
        assert entries[0]["payload"]["category_group"] == "ЖЕНСКОЕ ЗДОРОВЬЕ"


# ---------------------------------------------------------------------------
# Test 2: two_level_filter_structure — JS-side, tested via data shape
# ---------------------------------------------------------------------------

def test_two_level_filter_data_shape():
    """Symptom entries have both parent_group and category_group for 2-level UI."""
    lines = [
        "ОПОРНО-ДВИГАТЕЛЬНЫЙ АППАРАТ",
        "  СУСТАВЫ",
        "Артрит",
        "Одинарные: Лаванда",
        "",
        "  МЫШЦЫ",
        "Миалгия",
        "Одинарные: Розмарин",
        "",
    ]
    entries = parser.parse_symptoms(lines, sym_start=0)

    assert len(entries) >= 1
    for entry in entries:
        payload = entry["payload"]
        assert "parent_group" in payload
        assert "category_group" in payload
        # Both parent and child present for sub-entries
        if payload["category_group"] in ("СУСТАВЫ", "МЫШЦЫ"):
            assert payload["parent_group"] == "ОПОРНО-ДВИГАТЕЛЬНЫЙ АППАРАТ"


# ---------------------------------------------------------------------------
# Test 3: reseed script can read and process items with parent_group
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_reseed_upserts_parent_group(tmp_path):
    """reseed_symptom_hierarchy updates parent_group on existing symptom cards."""
    import json
    import scripts.reseed_symptom_hierarchy as reseeder

    # Create a fake symptom card in DB
    from db.session import AsyncSessionLocal
    from db.models import AromaCardModel

    async with AsyncSessionLocal() as session:
        card = AromaCardModel(
            slug="symptom-test-panicka",
            name="Паническая атака",
            category="symptom",
            source_type="symptom",
            aliases=[],
            payload={"category_group": "ТРЕВОЖНЫЕ РАССТРОЙСТВА", "description": ""},
        )
        session.add(card)
        await session.commit()

    # Write a fake pdf_symptoms.json
    fake_data = [
        {
            "slug": "symptom-test-panicka",
            "name": "Паническая атака",
            "payload": {
                "parent_group": "НЕРВНАЯ СИСТЕМА",
                "category_group": "ТРЕВОЖНЫЕ РАССТРОЙСТВА",
            },
        }
    ]
    fake_file = tmp_path / "pdf_symptoms.json"
    fake_file.write_text(json.dumps(fake_data), encoding="utf-8")

    with patch.object(reseeder, "SYMPTOMS_FILE", fake_file):
        updated = await reseeder.run(dry_run=False)

    assert updated == 1

    from sqlalchemy import select
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AromaCardModel).where(AromaCardModel.slug == "symptom-test-panicka")
        )
        card = result.scalar_one()

    assert card.payload["parent_group"] == "НЕРВНАЯ СИСТЕМА"
    assert card.payload["category_group"] == "ТРЕВОЖНЫЕ РАССТРОЙСТВА"
