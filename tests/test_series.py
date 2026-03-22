"""Tests for Content Series feature."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Series Templates
# ---------------------------------------------------------------------------


def test_templates_file_valid():
    templates_path = Path(__file__).resolve().parents[1] / "data" / "series_templates.json"
    assert templates_path.exists(), "series_templates.json not found"
    templates = json.loads(templates_path.read_text())
    assert isinstance(templates, list)
    assert len(templates) == 5

    for t in templates:
        assert "key" in t
        assert "label" in t
        assert "post_count" in t
        assert "positions" in t
        assert isinstance(t["positions"], list)
        assert len(t["positions"]) == t["post_count"]
        for pos in t["positions"]:
            assert pos["role"] in ("intro", "middle", "climax", "cta")
            assert "hint" in pos


def test_templates_roles_correct():
    """First post is always intro, last is cta, second-to-last is climax."""
    templates_path = Path(__file__).resolve().parents[1] / "data" / "series_templates.json"
    templates = json.loads(templates_path.read_text())
    for t in templates:
        positions = t["positions"]
        assert positions[0]["role"] == "intro", f"Template {t['key']}: first post should be intro"
        assert positions[-1]["role"] == "cta", f"Template {t['key']}: last post should be cta"
        if len(positions) >= 3:
            assert positions[-2]["role"] == "climax", f"Template {t['key']}: second-to-last should be climax"


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def test_parse_outline():
    from bot.agents.series_orchestrator import _parse_outline

    raw = """POST 1: Знакомство с лавандой
ANGLE: Первое впечатление и аромат
ROLE: intro

POST 2: Терапевтические свойства
ANGLE: Что умеет лаванда
ROLE: middle

POST 3: Применение в жизни
ANGLE: Практические рецепты
ROLE: middle

POST 4: История лаванды
ANGLE: Культурный контекст
ROLE: climax

POST 5: Итоги серии
ANGLE: Собираем вместе
ROLE: cta

SUMMARY: Серия о лаванде как универсальном масле для каждого дня"""

    outline = _parse_outline(raw, 5, "Лаванда")
    assert len(outline["positions"]) == 5
    assert outline["positions"][0]["role"] == "intro"
    assert outline["positions"][0]["title"] == "Знакомство с лавандой"
    assert outline["positions"][-1]["role"] == "cta"
    assert outline["positions"][-2]["role"] == "climax"
    assert "лаванд" in outline["summary"].lower()


def test_parse_outline_fills_missing():
    from bot.agents.series_orchestrator import _parse_outline

    raw = """POST 1: Intro
ROLE: intro

POST 2: Middle
ROLE: middle"""

    outline = _parse_outline(raw, 5, "Тест")
    assert len(outline["positions"]) == 5
    assert outline["positions"][0]["role"] == "intro"
    assert outline["positions"][-1]["role"] == "cta"
    assert outline["positions"][-2]["role"] == "climax"


def test_parse_outline_enforces_roles():
    """Even if Claude assigns wrong roles, enforce constraints."""
    from bot.agents.series_orchestrator import _parse_outline

    raw = """POST 1: First
ROLE: middle

POST 2: Second
ROLE: middle

POST 3: Third
ROLE: middle"""

    outline = _parse_outline(raw, 3, "Тест")
    assert outline["positions"][0]["role"] == "intro"
    assert outline["positions"][-1]["role"] == "cta"


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------


def test_parse_posts_batch():
    from bot.agents.series_writer import _parse_posts_batch

    raw = """===POST 1===
CAPTION: Знаете момент, когда вечером наконец выдыхаешь?
CTA: Сохраняй, чтобы не потерять
VISUAL_PROMPT: lavender field sunset soft light

===POST 2===
CAPTION: Лаванда, это больше чем запах перед сном.
CTA: Напиши в директ
VISUAL_PROMPT: essential oil bottle botanical"""

    positions = [{"index": 0}, {"index": 1}]
    posts = _parse_posts_batch(raw, positions)
    assert len(posts) == 2
    assert "выдыхаешь" in posts[0]["caption"]
    assert "Лаванда" in posts[1]["caption"]
    assert posts[0]["visual_prompt"] == "lavender field sunset soft light"


def test_summarize_posts():
    from bot.agents.series_writer import summarize_posts

    posts = [
        {"index": 0, "caption": "Знаете момент, когда вечером наконец выдыхаешь?"},
        {"index": 1, "caption": "Лаванда, это больше чем запах."},
    ]
    result = summarize_posts(posts)
    assert "Пост 1" in result
    assert "Пост 2" in result
    assert "выдыхаешь" in result


# ---------------------------------------------------------------------------
# Coherence
# ---------------------------------------------------------------------------


def test_parse_coherence():
    from bot.agents.series_coherence import _parse_coherence

    raw = """SCORE: 0.85
ISSUES: Пост 3 повторяет идею из поста 2; Финал слишком резкий
SUGGESTION: Добавить переход между постами 2 и 3"""

    result = _parse_coherence(raw)
    assert result["score"] == 0.85
    assert len(result["issues"]) == 2
    assert "повторяет" in result["issues"][0]
    assert "переход" in result["suggestion"]


def test_parse_coherence_perfect():
    from bot.agents.series_coherence import _parse_coherence

    raw = """SCORE: 1.0
ISSUES: нет
SUGGESTION: нет"""

    result = _parse_coherence(raw)
    assert result["score"] == 1.0
    assert result["issues"] == []
    assert result["suggestion"] == ""


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------


def test_outline_prompt():
    from bot.agents.prompts.series_prompts import outline_prompt

    result = outline_prompt(
        topic="Лаванда: масло недели",
        goal_key="trust",
        format_key="instagram",
        post_count=5,
        template_hint="Знакомство → свойства → применение → история → итог",
        goal_guidance={"trust": "Доверие"},
        format_labels={"instagram": "Instagram"},
    )
    assert "Лаванда" in result
    assert "5" in result
    assert "POST 1" in result


def test_outline_prompt_with_rag():
    from bot.agents.prompts.series_prompts import outline_prompt

    rag = "## Релевантные данные\n### Лаванда\nСедатив, антисептик"
    result = outline_prompt(
        topic="Лаванда",
        goal_key="trust",
        format_key="instagram",
        post_count=5,
        template_hint="test",
        goal_guidance={"trust": "Доверие"},
        format_labels={"instagram": "Instagram"},
        rag_context=rag,
    )
    assert "Седатив" in result


def test_writer_batch_prompt():
    from bot.agents.prompts.series_prompts import writer_batch_prompt

    positions = [
        {"index": 0, "title": "Intro", "role": "intro"},
        {"index": 1, "title": "Middle", "role": "middle"},
    ]
    result = writer_batch_prompt(
        topic="Тест",
        goal_key="trust",
        format_key="instagram",
        outline_text="Plan...",
        positions=positions,
        previous_summaries="",
        goal_guidance={"trust": "Доверие"},
    )
    assert "POST 1" in result
    assert "POST 2" in result
    assert "===POST 1===" in result


def test_coherence_prompt():
    from bot.agents.prompts.series_prompts import coherence_prompt

    result = coherence_prompt("Тест", "Пост 1...\nПост 2...", 2)
    assert "SCORE:" in result
    assert "ISSUES:" in result


# ---------------------------------------------------------------------------
# Generation task (integration-level, mocked Claude)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_complete_series_generation_mocked():
    """Test the full generation pipeline with mocked Claude calls."""
    from bot.services.drafts_store import get_draft, save_draft

    # Create stub draft
    stub = await save_draft(
        kind="content_series",
        topic="Лаванда: масло недели",
        source="/test",
        payload={"generation_pending": True, "post_count": 3, "template_key": "custom"},
    )

    outline_response = """POST 1: Знакомство
ANGLE: Первое впечатление
ROLE: intro

POST 2: Свойства
ANGLE: Deep dive
ROLE: middle

POST 3: Итог
ANGLE: Завершение
ROLE: cta

SUMMARY: Серия о лаванде"""

    writer_response = """===POST 1===
CAPTION: Знаете момент, когда вечером наконец выдыхаешь?
CTA: Сохрани
VISUAL_PROMPT: lavender field

===POST 2===
CAPTION: Лаванда это больше чем запах
CTA: Попробуй
VISUAL_PROMPT: essential oil

===POST 3===
CAPTION: За эту неделю мы узнали о лаванде всё
CTA: Записаться
VISUAL_PROMPT: person relaxing"""

    coherence_response = """SCORE: 0.9
ISSUES: нет
SUGGESTION: нет"""

    call_count = {"n": 0}
    responses = [outline_response, writer_response, coherence_response]

    def mock_claude(**kwargs):
        idx = min(call_count["n"], len(responses) - 1)
        call_count["n"] += 1
        return responses[idx]

    with patch("bot.services.claude_client.call_claude", side_effect=mock_claude), \
         patch("bot.services.rag.retriever.retrieve_relevant_cards", return_value=[]):
        from miniapp.api.generation.series import complete_series_generation
        await complete_series_generation(
            stub.draft_id, "Лаванда: масло недели", "trust", "instagram", 3, "custom",
        )

    draft = await get_draft(stub.draft_id)
    assert draft is not None
    payload = draft.payload
    assert payload.get("generation_pending") is False
    assert len(payload.get("series_posts", [])) == 3
    assert payload["series_posts"][0]["caption"] != ""
    assert payload["series_posts"][0]["role"] == "intro"
    assert payload["series_posts"][-1]["role"] == "cta"
    assert payload.get("coherence_score") is not None


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


def test_content_series_create_request():
    from miniapp.api.models import ContentSeriesCreateRequest

    req = ContentSeriesCreateRequest(topic="test", post_count=5)
    assert req.post_count == 5
    assert req.goal_key == "trust"
    assert req.format_key == "instagram"

    # Bounds check
    with pytest.raises(Exception):
        ContentSeriesCreateRequest(topic="test", post_count=1)
    with pytest.raises(Exception):
        ContentSeriesCreateRequest(topic="test", post_count=10)


# ---------------------------------------------------------------------------
# Series templates API
# ---------------------------------------------------------------------------


def test_get_series_templates():
    from miniapp.api.generation.series import get_series_templates

    templates = get_series_templates()
    assert len(templates) == 5
    assert templates[0]["key"] == "oil_of_week"
