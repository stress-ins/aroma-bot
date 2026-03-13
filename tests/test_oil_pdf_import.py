"""Tests for scripts/import_oil_pdfs.py"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure project root is on path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.import_oil_pdfs as importer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MOCK_PDF_TEXT = """\
ЛАВАНДА (Lavandula angustifolia)
Ботаническое семейство: Яснотковые
Страна происхождения: Франция, Болгария
Способ получения: Паровая дистилляция
Ключ: Успокоение и гармония
Летучесть: Средняя (middle note)
Действие на НПС: Балансирует нервную систему
Терапевтические свойства: Снимает стресс, помогает при тревоге, улучшает сон
Психологические свойства: Мягко успокаивает внутренний диалог
Ресурсные значения «+» и «-»
«+» – Спокойствие, принятие, покой
«-» – Тревога, беспокойство, нервозность
"""

_MOCK_CLAUDE_RESPONSE = {
    "name": "Лаванда",
    "description": "Лаванда (Lavandula angustifolia) — одно из самых универсальных эфирных масел. Балансирующее масло, помогает при стрессе и тревоге, улучшает качество сна.",
    "description_short": "Лаванда — балансирующее масло покоя и поддержки. Снимает тревогу, улучшает сон.",
    "therapeutic_properties": "Снимает стресс, помогает при тревоге, улучшает сон",
    "psychological_properties": "Мягко успокаивает внутренний диалог",
    "botanical_family": "Яснотковые",
    "extraction_method": "Паровая дистилляция",
    "contraindications": "",
    "origin_countries": "Франция, Болгария",
    "key": "Успокоение и гармония",
    "volatility": "Средняя (middle note)",
    "resource_plus": "Спокойствие, принятие, покой",
    "resource_minus": "Тревога, беспокойство, нервозность",
    "questions": "Где не хватает покоя?; Что мешает расслабиться?",
    "nps_effect": "Адаптоген, балансирует нервную систему",
    "history": "Используется более 2500 лет в медицине и косметологии",
    "applications": "Диффузия 3-5 капель; 2% в базовом масле для массажа",
    "precautions": "Избегать при аллергии на растения семейства Яснотковые",
    "conditions_for_use": "Стресс, тревога, бессонница, головная боль",
}


# ---------------------------------------------------------------------------
# Test 1: dry-run does not modify DB
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dry_run_does_not_write_to_db(tmp_path):
    """--dry-run must not upsert anything into the DB."""
    # Create a fake PDF file
    fake_pdf = tmp_path / "ЛАВАНДА.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 fake content")

    with (
        patch.object(importer, "PDF_DIR", tmp_path),
        patch.object(importer, "_extract_text_pdfplumber", return_value=_MOCK_PDF_TEXT),
        patch.object(importer, "_parse_with_claude", return_value=_MOCK_CLAUDE_RESPONSE),
        patch.object(importer, "_upsert_card", new_callable=AsyncMock) as mock_upsert,
    ):
        processed = await importer.run(dry_run=True)

    # _upsert_card must never be called in dry-run mode
    mock_upsert.assert_not_called()
    # But the slug should still appear in the result
    assert "lavender" in processed


# ---------------------------------------------------------------------------
# Test 2: dry-run returns list of found PDFs
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dry_run_returns_slug_list(tmp_path):
    """dry-run returns all processable slugs even without DB writes."""
    # Create fake PDFs for two oils
    (tmp_path / "ЛАВАНДА.pdf").write_bytes(b"%PDF fake")
    (tmp_path / "БЕРГАМОТ.pdf").write_bytes(b"%PDF fake")

    with (
        patch.object(importer, "PDF_DIR", tmp_path),
        patch.object(importer, "_extract_text_pdfplumber", return_value=_MOCK_PDF_TEXT),
        patch.object(importer, "_parse_with_claude", return_value=_MOCK_CLAUDE_RESPONSE),
        patch.object(importer, "_upsert_card", new_callable=AsyncMock),
    ):
        processed = await importer.run(dry_run=True)

    assert "lavender" in processed
    assert "bergamot" in processed


# ---------------------------------------------------------------------------
# Test 3: parsing text → structured fields (mock PDF text)
# ---------------------------------------------------------------------------

def test_parse_with_claude_returns_dict():
    """_parse_with_claude parses JSON returned by Claude."""
    mock_client = MagicMock()
    mock_content = MagicMock()
    mock_content.text = json.dumps(_MOCK_CLAUDE_RESPONSE)
    mock_client.messages.create.return_value = MagicMock(content=[mock_content])

    with patch("anthropic.Anthropic", return_value=mock_client):
        result = importer._parse_with_claude(_MOCK_PDF_TEXT, api_key="fake-key")

    assert result["name"] == "Лаванда"
    assert result["botanical_family"] == "Яснотковые"
    assert result["key"] == "Успокоение и гармония"


def test_parse_with_claude_handles_markdown_wrapped_json():
    """_parse_with_claude strips ``` code block wrapping if present."""
    mock_client = MagicMock()
    mock_content = MagicMock()
    mock_content.text = f"```json\n{json.dumps(_MOCK_CLAUDE_RESPONSE)}\n```"
    mock_client.messages.create.return_value = MagicMock(content=[mock_content])

    with patch("anthropic.Anthropic", return_value=mock_client):
        result = importer._parse_with_claude(_MOCK_PDF_TEXT, api_key="fake-key")

    assert result["name"] == "Лаванда"


# ---------------------------------------------------------------------------
# Test 4: upsert creates new card; second call updates, not duplicates
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_upsert_creates_and_updates_without_duplicate():
    """_upsert_card creates once, then updates on second call — no duplicate rows."""
    from db.session import AsyncSessionLocal
    from db.models import AromaCardModel
    from sqlalchemy import select

    # First upsert: should create
    action1 = await importer._upsert_card(
        slug="lavender-test",
        name="Лаванда Тест",
        source_type="flower",
        aliases=[],
        payload={"description": "v1"},
    )
    assert action1 == "created"

    # Second upsert: should update
    action2 = await importer._upsert_card(
        slug="lavender-test",
        name="Лаванда Тест Обновлённая",
        source_type="flower",
        aliases=["Лаванда"],
        payload={"description": "v2"},
    )
    assert action2 == "updated"

    # Exactly one row in DB
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AromaCardModel).where(AromaCardModel.slug == "lavender-test")
        )
        rows = result.scalars().all()

    assert len(rows) == 1
    assert rows[0].name == "Лаванда Тест Обновлённая"
    assert rows[0].payload["description"] == "v2"


# ---------------------------------------------------------------------------
# Test 5: after import, KB lookup finds the oil
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_kb_lookup_finds_imported_oil():
    """After upsert, KBContextBuilder can find the oil by keyword."""
    from bot.services.kb_context_builder import build_content_context

    # Insert a card
    await importer._upsert_card(
        slug="lavender-kb",
        name="Лаванда КБ",
        source_type="flower",
        aliases=["lavender"],
        payload={
            "description": "Балансирующее масло для сна и покоя",
            "key": "Успокоение",
        },
    )

    ctx = await build_content_context("Лаванда КБ", platform="instagram", max_cards=5)
    slugs = [c["slug"] for c in ctx.cards]
    assert "lavender-kb" in slugs


# ---------------------------------------------------------------------------
# Test 6: --file filter works correctly
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_file_filter_processes_only_specified_oil(tmp_path):
    """--file flag restricts processing to a single PDF."""
    for stem in ("ЛАВАНДА", "БЕРГАМОТ", "РОЗА"):
        (tmp_path / f"{stem}.pdf").write_bytes(b"%PDF fake")

    with (
        patch.object(importer, "PDF_DIR", tmp_path),
        patch.object(importer, "_extract_text_pdfplumber", return_value=_MOCK_PDF_TEXT),
        patch.object(importer, "_parse_with_claude", return_value=_MOCK_CLAUDE_RESPONSE),
        patch.object(importer, "_upsert_card", new_callable=AsyncMock) as mock_upsert,
    ):
        processed = await importer.run(dry_run=False, only_file="ЛАВАНДА")

    assert processed == ["lavender"]
    mock_upsert.assert_called_once()


# ---------------------------------------------------------------------------
# Test 7: graceful skip when PDF text is empty
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_graceful_skip_empty_pdf(tmp_path):
    """If pdfplumber returns empty text, the file is skipped without error."""
    (tmp_path / "ЛАВАНДА.pdf").write_bytes(b"%PDF fake")

    with (
        patch.object(importer, "PDF_DIR", tmp_path),
        patch.object(importer, "_extract_text_pdfplumber", return_value="   "),
        patch.object(importer, "_upsert_card", new_callable=AsyncMock) as mock_upsert,
    ):
        processed = await importer.run(dry_run=False, only_file="ЛАВАНДА")

    assert processed == []
    mock_upsert.assert_not_called()


# ---------------------------------------------------------------------------
# Test 8: second upsert merges payload, does not overwrite existing keys
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_upsert_merges_with_existing_payload():
    """Second upsert must merge payload, preserving keys not present in new data."""
    # First upsert: seed with cross-refs and resource_values
    await importer._upsert_card(
        slug="lavender-merge-test",
        name="Лаванда Мерж",
        source_type="flower",
        aliases=[],
        payload={
            "description": "old description",
            "cross_refs": ["ylang-ylang", "bergamot"],
            "resource_values": {"plus": "Спокойствие", "minus": "Тревога"},
        },
    )

    # Second upsert: new PDF data with description_short but no cross_refs
    await importer._upsert_card(
        slug="lavender-merge-test",
        name="Лаванда Мерж",
        source_type="flower",
        aliases=[],
        payload={
            "description": "new description from pdf",
            "description_short": "Краткое описание",
        },
    )

    from db.session import AsyncSessionLocal
    from db.models import AromaCardModel
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AromaCardModel).where(AromaCardModel.slug == "lavender-merge-test")
        )
        card = result.scalar_one()

    # New fields updated
    assert card.payload["description"] == "new description from pdf"
    assert card.payload["description_short"] == "Краткое описание"
    # Existing seed data preserved
    assert card.payload["cross_refs"] == ["ylang-ylang", "bergamot"]
    assert card.payload["resource_values"]["plus"] == "Спокойствие"


# ---------------------------------------------------------------------------
# Test 9: parse returns description_short field
# ---------------------------------------------------------------------------

def test_parse_returns_description_short():
    """_parse_with_claude must return description_short distinct from description."""
    mock_client = MagicMock()
    mock_content = MagicMock()
    mock_content.text = json.dumps(_MOCK_CLAUDE_RESPONSE)
    mock_client.messages.create.return_value = MagicMock(content=[mock_content])

    with patch("anthropic.Anthropic", return_value=mock_client):
        result = importer._parse_with_claude(_MOCK_PDF_TEXT, api_key="fake-key")

    assert "description_short" in result
    assert result["description_short"]  # non-empty
    assert result["description_short"] != result["description"]


# ---------------------------------------------------------------------------
# Test 10: parse returns resource_values structure
# ---------------------------------------------------------------------------

def test_parse_returns_resource_values():
    """_parse_with_claude must return resource_plus and resource_minus fields."""
    mock_client = MagicMock()
    mock_content = MagicMock()
    mock_content.text = json.dumps(_MOCK_CLAUDE_RESPONSE)
    mock_client.messages.create.return_value = MagicMock(content=[mock_content])

    with patch("anthropic.Anthropic", return_value=mock_client):
        result = importer._parse_with_claude(_MOCK_PDF_TEXT, api_key="fake-key")

    assert "resource_plus" in result
    assert "resource_minus" in result
    assert result["resource_plus"]
    assert result["resource_minus"]
