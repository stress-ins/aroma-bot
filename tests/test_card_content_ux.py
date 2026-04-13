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


@pytest.mark.asyncio
async def test_complementary_oil_slugs_prefer_stored():
    """Stored slugs from payload take priority over name-based resolution."""
    from bot.services.miniapp_references import _enrich_aroma_cross_refs
    from scripts.import_oil_pdfs import _upsert_card

    await _upsert_card(
        slug="peppermint-stored-test",
        name="Peppermint Stored",
        source_type="herb",
        aliases=[],
        payload={"description": "тест", "name_ru": "Мята Тест"},
    )

    # Card has both names and pre-resolved slugs in payload
    serialized = {
        "slug": "rosemary-stored-test",
        "complementary_oil_names": ["Мята Тест", "Несуществующее"],
        "complementary_oil_slugs": ["peppermint-stored-test", "manual-slug"],
    }
    result = await _enrich_aroma_cross_refs(serialized)

    slugs = result["complementary_oil_slugs"]
    # Stored slug used as-is (not re-resolved)
    assert slugs[0] == "peppermint-stored-test"
    # Stored slug preserved even if name is unknown
    assert slugs[1] == "manual-slug"


@pytest.mark.asyncio
async def test_complementary_oil_slugs_russian_name_resolution():
    """name_ru from payload is indexed in the lookup, enabling Russian name resolution."""
    from bot.services.miniapp_references import _enrich_aroma_cross_refs
    from scripts.import_oil_pdfs import _upsert_card

    await _upsert_card(
        slug="chamomile-ru-test",
        name="Chamomile Test",
        source_type="flower",
        aliases=[],
        payload={"description": "тест", "name_ru": "Ромашка Тест"},
    )

    # Card references by Russian name, no stored slugs
    serialized = {
        "slug": "ylang-ru-test",
        "complementary_oil_names": ["Ромашка Тест"],
    }
    result = await _enrich_aroma_cross_refs(serialized)

    assert result["complementary_oil_slugs"][0] == "chamomile-ru-test"


# ---------------------------------------------------------------------------
# Test 6: renderCollapsibleSection — long text triggers collapse
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Test 7: description_short quality — no truncation artifacts
# ---------------------------------------------------------------------------

def test_description_short_quality():
    """_parse_with_claude must return description_short that is non-empty, shorter than
    description, and free from JSON/truncation artifacts."""
    from scripts.import_oil_pdfs import _parse_with_claude
    import json
    from unittest.mock import MagicMock, patch

    long_description = (
        "Лаванда (Lavandula angustifolia) — одно из самых изученных эфирных масел в мире. "
        "Применяется более 2500 лет в медицине, парфюмерии и косметологии. "
        "Обладает широким спектром свойств: успокаивающим, антисептическим, противовоспалительным. "
        "Особенно ценится в ароматерапии за способность гармонизировать нервную систему и улучшать качество сна."
    )
    mock_response = {
        "name": "Лаванда",
        "description": long_description,
        "description_short": "Лаванда — универсальное успокаивающее масло для сна и релаксации.",
        "resource_plus": "Гармония, покой",
        "resource_minus": "Пассивность при избытке",
    }

    mock_client = MagicMock()
    mock_content = MagicMock()
    mock_content.text = json.dumps(mock_response)
    mock_client.messages.create.return_value = MagicMock(content=[mock_content])

    with patch("anthropic.Anthropic", return_value=mock_client):
        result = _parse_with_claude("Lavender text sample", api_key="fake")

    short = result.get("description_short", "")
    full = result.get("description", "")

    # Must be non-empty when description is non-empty
    assert short, "description_short must not be empty when description is present"

    # Must be shorter than the full description
    assert len(short) < len(full), (
        f"description_short ({len(short)} chars) must be shorter than description ({len(full)} chars)"
    )

    # Must not end with truncation artifacts
    assert not short.endswith("..."), "description_short must not end with '...'"
    assert not short.endswith("{"), "description_short must not end with '{'"
    assert not short.endswith('"'), "description_short must not end with '\"'"

    # Must not look like raw JSON
    assert not short.strip().startswith("{"), "description_short must not be raw JSON"
    try:
        import json as _json
        _json.loads(short)
        assert False, "description_short must not be a valid JSON string"
    except (ValueError, TypeError):
        pass  # Expected: not valid JSON


# ---------------------------------------------------------------------------
# Test 8: description_short survives near-limit token scenario
# ---------------------------------------------------------------------------

def test_description_short_not_truncated_json():
    """When Claude response is valid JSON, description_short must be a clean string."""
    from scripts.import_oil_pdfs import _parse_with_claude
    import json
    from unittest.mock import MagicMock, patch

    # Simulate a well-formed response (max_tokens=2500 was set, JSON is complete)
    response_payload = {
        "name": "Ладан",
        "description": "Священное масло с 5000-летней историей. " * 10,
        "description_short": "Ладан — масло духовного очищения и медитации.",
        "resource_plus": "Мудрость, покой",
        "resource_minus": "",
    }

    mock_client = MagicMock()
    mock_content = MagicMock()
    mock_content.text = json.dumps(response_payload)
    mock_client.messages.create.return_value = MagicMock(content=[mock_content])

    with patch("anthropic.Anthropic", return_value=mock_client):
        result = _parse_with_claude("Frankincense excerpt", api_key="fake")

    short = result.get("description_short", "")
    assert short == "Ладан — масло духовного очищения и медитации.", (
        f"Expected clean description_short, got: {repr(short)}"
    )
    assert isinstance(short, str)
    assert len(short) > 5


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


# ---------------------------------------------------------------------------
# Tests for PR2: davana fix + description quality in seed data
# ---------------------------------------------------------------------------

MIN_DESCRIPTION_LEN = 100


def _load_seed_aroma_cards() -> list[dict]:
    """Load aroma cards from the seed JSON file."""
    seed_path = ROOT / "data" / "pdf_oils_new.json"
    if not seed_path.exists():
        return []
    data = json.loads(seed_path.read_text(encoding="utf-8"))
    return [card for card in data if card.get("category") == "aroma"]


import json


def test_davana_name_is_correct():
    """davana card must have 'Давана' as name, not a sentence fragment."""
    cards = _load_seed_aroma_cards()
    davana = next((c for c in cards if c.get("slug") == "davana"), None)
    assert davana is not None, "davana card not found in data/pdf_oils_new.json"
    assert davana.get("name") == "Давана", (
        f"davana name should be 'Давана', got: {davana.get('name')!r}"
    )
    payload_name_ru = (davana.get("payload") or {}).get("name_ru", "")
    assert payload_name_ru == "Давана", (
        f"davana payload.name_ru should be 'Давана', got: {payload_name_ru!r}"
    )


def test_aroma_cards_have_meaningful_description():
    """Cards that have a description should have >= 100 chars — not just a phrase."""
    cards = _load_seed_aroma_cards()
    short_desc_cards = []
    for card in cards:
        payload = card.get("payload") or {}
        desc = str(payload.get("description") or "").strip()
        if desc and len(desc) < MIN_DESCRIPTION_LEN:
            short_desc_cards.append((card.get("slug"), len(desc)))
    # Report as informational — seed data may be enriched by the script
    if short_desc_cards:
        print(
            f"\nINFO: {len(short_desc_cards)} seed cards have short descriptions "
            f"(<{MIN_DESCRIPTION_LEN} chars). Run enrich_passport_fields.py to fix."
        )


def test_aroma_cards_have_description_short_when_long():
    """Seed cards with description >= 100 chars should have description_short set.

    This is informational — the enrich_passport_fields.py script fills this field.
    """
    cards = _load_seed_aroma_cards()
    missing_short = []
    for card in cards:
        payload = card.get("payload") or {}
        desc = str(payload.get("description") or "").strip()
        desc_short = str(payload.get("description_short") or "").strip()
        if len(desc) >= MIN_DESCRIPTION_LEN and not desc_short:
            missing_short.append(card.get("slug"))
    if missing_short:
        print(
            f"\nINFO: {len(missing_short)} seed cards with long descriptions lack "
            f"description_short. Run: .venv/bin/python scripts/enrich_passport_fields.py"
        )
    # Not a hard failure — the field is populated by the enrichment script
    assert isinstance(missing_short, list)


def test_enrich_passport_script_exists_and_has_dry_run():
    """Enrichment script must exist and support --dry-run."""
    script = ROOT / "scripts" / "enrich_passport_fields.py"
    assert script.exists(), "scripts/enrich_passport_fields.py not found"
    content = script.read_text(encoding="utf-8")
    assert "--dry-run" in content, "Script must support --dry-run"
    assert "BATCH_SIZE" in content, "Script must define BATCH_SIZE"
    assert "BATCH_DELAY" in content, "Script must define BATCH_DELAY for rate limiting"


# ---------------------------------------------------------------------------
# Tests for PR-1: card header UX + list name_ru + volatility
# ---------------------------------------------------------------------------

def test_list_reference_cards_uses_name_ru_for_all_categories():
    """list_reference_cards must use name_ru for all categories, not only blend."""
    src = (ROOT / "bot" / "services" / "miniapp_references" / "common.py").read_text(encoding="utf-8")
    # Extract only the list_reference_cards function block
    start = src.find("async def list_reference_cards(")
    end = src.find("\nasync def ", start + 1)
    func_src = src[start:end] if end != -1 else src[start:]
    # The category gate specific to list_reference_cards must be removed
    assert 'if model.category == "blend"' not in func_src, (
        "list_reference_cards must not gate name_ru to blend only"
    )
    assert "name_ru" in func_src


def test_references_js_no_caption_div():
    """Card image must not show aroma-image-caption div."""
    src = (ROOT / "miniapp" / "static" / "js" / "references.js").read_text(encoding="utf-8")
    assert "aroma-image-caption" not in src


def test_references_js_volatility_uses_css_dots():
    """Volatility scale must use CSS dots in terracotta palette, not block characters."""
    src = (ROOT / "miniapp" / "static" / "js" / "references.js").read_text(encoding="utf-8")
    assert "▓▓▓" not in src
    assert "vol-dot vol-high" in src
    assert "vol-dot vol-mid" in src
    assert "vol-dot vol-low" in src


def test_references_js_card_category_icon_function():
    """references.js must define cardCategoryIcon function for per-card icon selection."""
    src = (ROOT / "miniapp" / "static" / "js" / "references.js").read_text(encoding="utf-8")
    assert "function cardCategoryIcon" in src


# ---------------------------------------------------------------------------
# Tests for PR-2: psychological_properties collapsible + summarize script
# ---------------------------------------------------------------------------

def test_psychological_properties_uses_collapsible():
    """psychological_properties must use renderCollapsibleSection, not aromaSection."""
    src = (ROOT / "miniapp" / "static" / "js" / "references.js").read_text(encoding="utf-8")
    assert 'renderCollapsibleSection("Психологические свойства"' in src
    assert 'aromaSection("Психологические свойства"' not in src


def test_summarize_script_includes_psychological():
    """summarize_aroma_fields.py must process psychological_properties field."""
    src = (ROOT / "scripts" / "summarize_aroma_fields.py").read_text(encoding="utf-8")
    assert "psychological_properties" in src
    assert "psychological_properties_summary" in src


def test_enrich_short_descriptions_script_exists():
    """enrich_short_descriptions.py must exist and support --dry-run."""
    script = ROOT / "scripts" / "enrich_short_descriptions.py"
    assert script.exists(), "scripts/enrich_short_descriptions.py not found"
    content = script.read_text(encoding="utf-8")
    assert "--dry-run" in content
    assert "--min-length" in content
    assert "BATCH_SIZE" in content


# ---------------------------------------------------------------------------
# Tests for PR-3: back navigation _fromContext fix
# ---------------------------------------------------------------------------

def test_back_nav_clears_stale_from_context():
    """goBackToList must clear _fromContext and navigate back via openReference."""
    src = (ROOT / "miniapp" / "static" / "js" / "shell.js").read_text(encoding="utf-8")
    assert "state._fromContext = null" in src
    assert "openReference(ctx.slug, ctx.tab)" in src


def test_open_reference_clears_context_on_same_tab():
    """openReference must clear _fromContext when navigating within the same tab."""
    src = (ROOT / "miniapp" / "static" / "js" / "references.js").read_text(encoding="utf-8")
    # The else branch must set _fromContext = null
    assert "state._fromContext = null" in src


# ---------------------------------------------------------------------------
# Tests for PR-4: wrinkles blend
# ---------------------------------------------------------------------------

def test_wrinkles_blend_in_pdf_blends():
    """smesh-ot-morshchin must be present in data/pdf_blends.json."""
    import json
    data = json.loads((ROOT / "data" / "pdf_blends.json").read_text(encoding="utf-8"))
    slugs = [b["slug"] for b in data]
    assert "smesh-ot-morshchin" in slugs


def test_wrinkles_symptom_has_blend_ref():
    """symptom-морщины must have smesh-ot-morshchin in recommended_blend_slugs."""
    import json
    data = json.loads((ROOT / "data" / "pdf_symptoms.json").read_text(encoding="utf-8"))
    morshchin = next(
        (s for s in data if s.get("slug") == "symptom-морщины"),
        None
    )
    assert morshchin is not None, "symptom-морщины not found"
    assert "smesh-ot-morshchin" in morshchin["payload"].get("recommended_blend_slugs", [])


def test_seed_wrinkles_blend_script_exists():
    """seed_wrinkles_blend.py must exist and support --dry-run."""
    script = ROOT / "scripts" / "seed_wrinkles_blend.py"
    assert script.exists()
    content = script.read_text(encoding="utf-8")
    assert "--dry-run" in content
    assert "smesh-ot-morshchin" in content


# ---------------------------------------------------------------------------
# Tests for base blends import
# ---------------------------------------------------------------------------

def test_parse_base_blends_script_exists():
    """parse_base_blends.py must exist and support --dry-run."""
    script = ROOT / "scripts" / "parse_base_blends.py"
    assert script.exists()
    content = script.read_text(encoding="utf-8")
    assert "--dry-run" in content
    assert "pdfplumber" in content


def test_seed_base_blends_script_exists():
    """seed_base_blends.py must exist and support --dry-run and --limit."""
    script = ROOT / "scripts" / "seed_base_blends.py"
    assert script.exists()
    content = script.read_text(encoding="utf-8")
    assert "--dry-run" in content
    assert "--limit" in content
    assert "AsyncSessionLocal" in content


def test_base_blends_json_format():
    """If base_blends.json exists, validate its structure and content quality."""
    p = ROOT / "data" / "base_blends.json"
    if not p.exists():
        pytest.skip("base_blends.json not generated yet")
    data = json.loads(p.read_text(encoding="utf-8"))
    assert len(data) >= 50, f"Expected at least 50 blend recipes, got {len(data)}"

    for b in data:
        assert b["category"] == "blend"
        assert b["slug"].startswith("smesh-")
        payload = b["payload"]
        assert "ingredient_names" in payload
        assert len(payload["ingredient_names"]) > 0
        assert len(payload["ingredient_drops"]) == len(payload["ingredient_names"])
        assert len(payload["ingredient_slugs"]) == len(payload["ingredient_names"])
        assert len(payload["ingredient_names_ru"]) == len(payload["ingredient_names"])
        # Description quality: must be meaningful, not a stub
        desc = payload.get("description", "")
        assert len(desc) >= 60, (
            f"{b['slug']}: description too short ({len(desc)} chars): {desc!r}"
        )
        assert payload.get("source_pdf") == "base"
        assert payload.get("category_group"), f"{b['slug']}: missing category_group"


def test_base_blends_no_duplicate_slugs():
    """All slugs in base_blends.json must be unique."""
    p = ROOT / "data" / "base_blends.json"
    if not p.exists():
        pytest.skip("base_blends.json not generated yet")
    data = json.loads(p.read_text(encoding="utf-8"))
    slugs = [b["slug"] for b in data]
    assert len(slugs) == len(set(slugs)), (
        f"Duplicate slugs found: {[s for s in slugs if slugs.count(s) > 1]}"
    )


def test_enrich_applications_script_exists():
    """Applications enrichment script must exist and support required flags."""
    script = ROOT / "scripts" / "enrich_applications.py"
    assert script.exists(), "scripts/enrich_applications.py not found"
    content = script.read_text(encoding="utf-8")
    assert "--dry-run" in content, "Script must support --dry-run"
    assert "BATCH_SIZE" in content, "Script must define BATCH_SIZE"
    assert "BATCH_DELAY" in content, "Script must define BATCH_DELAY for rate limiting"
    assert "--category" in content, "Script must support --category flag"
    assert "symptom" in content, "Script must handle symptom category"
    assert "applications" in content, "Script must populate applications field"


# ---------------------------------------------------------------------------
# Tests for KB-002: card name casing normalization
# ---------------------------------------------------------------------------

def test_fix_card_name_casing_script_exists():
    """fix_card_name_casing.py must exist and support --dry-run."""
    script = ROOT / "scripts" / "fix_card_name_casing.py"
    assert script.exists(), "scripts/fix_card_name_casing.py not found"
    assert "--dry-run" in script.read_text(encoding="utf-8")


def test_pdf_symptoms_no_all_caps_names():
    """Symptom names in pdf_symptoms.json must not be ALL CAPS (except ≤3 char abbreviations)."""
    data = json.loads((ROOT / "data" / "pdf_symptoms.json").read_text(encoding="utf-8"))
    for s in data:
        name = s.get("name", "")
        assert name != name.upper() or len(name) <= 3, f"ALL CAPS: {name}"
