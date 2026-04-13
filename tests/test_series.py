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


def test_parse_outline_json():
    """Parse outline from JSON response (primary format)."""
    from bot.agents.series_orchestrator import _parse_outline

    raw = json.dumps({
        "summary": "Серия о лаванде как универсальном масле для каждого дня",
        "positions": [
            {"index": 1, "title": "Знакомство с лавандой", "angle": "Первое впечатление и аромат", "role": "intro"},
            {"index": 2, "title": "Терапевтические свойства", "angle": "Что умеет лаванда", "role": "middle"},
            {"index": 3, "title": "Применение в жизни", "angle": "Практические рецепты", "role": "middle"},
            {"index": 4, "title": "История лаванды", "angle": "Культурный контекст", "role": "climax"},
            {"index": 5, "title": "Итоги серии", "angle": "Собираем вместе", "role": "cta"},
        ],
    })

    outline = _parse_outline(raw, 5, "Лаванда")
    assert len(outline["positions"]) == 5
    assert outline["positions"][0]["role"] == "intro"
    assert outline["positions"][0]["title"] == "Знакомство с лавандой"
    assert outline["positions"][-1]["role"] == "cta"
    assert outline["positions"][-2]["role"] == "climax"
    assert "лаванд" in outline["summary"].lower()


def test_parse_outline_json_in_markdown_fence():
    """Parse outline from JSON wrapped in markdown fences."""
    from bot.agents.series_orchestrator import _parse_outline

    raw = '```json\n' + json.dumps({
        "summary": "Серия о лаванде",
        "positions": [
            {"index": 1, "title": "Intro", "angle": "A", "role": "intro"},
            {"index": 2, "title": "End", "angle": "B", "role": "cta"},
        ],
    }) + '\n```'

    outline = _parse_outline(raw, 2, "Лаванда")
    assert len(outline["positions"]) == 2
    assert outline["positions"][0]["role"] == "intro"


def test_parse_outline_legacy():
    """Legacy text format still works as fallback."""
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

    raw = json.dumps({
        "summary": "Тест",
        "positions": [
            {"index": 1, "title": "Intro", "angle": "", "role": "intro"},
            {"index": 2, "title": "Middle", "angle": "", "role": "middle"},
        ],
    })

    outline = _parse_outline(raw, 5, "Тест")
    assert len(outline["positions"]) == 5
    assert outline["positions"][0]["role"] == "intro"
    assert outline["positions"][-1]["role"] == "cta"
    assert outline["positions"][-2]["role"] == "climax"


def test_parse_outline_enforces_roles():
    """Even if Claude assigns wrong roles, enforce constraints."""
    from bot.agents.series_orchestrator import _parse_outline

    raw = json.dumps({
        "summary": "Тест",
        "positions": [
            {"index": 1, "title": "First", "angle": "", "role": "middle"},
            {"index": 2, "title": "Second", "angle": "", "role": "middle"},
            {"index": 3, "title": "Third", "angle": "", "role": "middle"},
        ],
    })

    outline = _parse_outline(raw, 3, "Тест")
    assert outline["positions"][0]["role"] == "intro"
    assert outline["positions"][-1]["role"] == "cta"


def test_parse_outline_string_index():
    """Claude sometimes returns index as string — must handle gracefully."""
    from bot.agents.series_orchestrator import _parse_outline

    raw = json.dumps({
        "summary": "Тест",
        "positions": [
            {"index": "1", "title": "First", "angle": "", "role": "intro"},
            {"index": "2", "title": "Second", "angle": "", "role": "cta"},
        ],
    })

    outline = _parse_outline(raw, 2, "Тест")
    assert len(outline["positions"]) == 2
    assert outline["positions"][0]["title"] == "First"
    assert outline["positions"][1]["title"] == "Second"


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------


def test_parse_posts_batch_json():
    """Parse posts from JSON response (primary format)."""
    from bot.agents.series_writer import _parse_posts_batch

    raw = json.dumps([
        {
            "index": 1,
            "caption": "Знаете момент, когда вечером наконец выдыхаешь?",
            "cta": "Сохраняй, чтобы не потерять",
            "visual_prompt": "lavender field sunset soft light",
        },
        {
            "index": 2,
            "caption": "Лаванда, это больше чем запах перед сном.",
            "cta": "Напиши в директ",
            "visual_prompt": "essential oil bottle botanical",
        },
    ])

    positions = [{"index": 0}, {"index": 1}]
    posts = _parse_posts_batch(raw, positions)
    assert len(posts) == 2
    assert "выдыхаешь" in posts[0]["caption"]
    assert "Лаванда" in posts[1]["caption"]
    assert posts[0]["visual_prompt"] == "lavender field sunset soft light"


def test_parse_posts_batch_string_index():
    """Claude sometimes returns index as string — must handle gracefully."""
    from bot.agents.series_writer import _parse_posts_batch

    raw = json.dumps([
        {"index": "1", "caption": "Первый пост", "cta": "", "visual_prompt": "test"},
        {"index": "2", "caption": "Второй пост", "cta": "", "visual_prompt": "test2"},
    ])

    positions = [{"index": 0}, {"index": 1}]
    posts = _parse_posts_batch(raw, positions)
    assert len(posts) == 2
    assert "Первый" in posts[0]["caption"]
    assert "Второй" in posts[1]["caption"]


def test_parse_posts_batch_json_in_markdown():
    """Parse posts from JSON wrapped in markdown fences."""
    from bot.agents.series_writer import _parse_posts_batch

    raw = '```json\n' + json.dumps([
        {"index": 1, "caption": "Пост один", "cta": "", "visual_prompt": "test"},
    ]) + '\n```'

    positions = [{"index": 0}]
    posts = _parse_posts_batch(raw, positions)
    assert len(posts) == 1
    assert "один" in posts[0]["caption"]


def test_parse_posts_batch_legacy():
    """Legacy ===POST N=== format still works as fallback."""
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


def test_parse_coherence_json():
    """Parse coherence from JSON response (primary format)."""
    from bot.agents.series_coherence import _parse_coherence

    raw = json.dumps({
        "score": 0.85,
        "issues": ["Пост 3 повторяет идею из поста 2", "Финал слишком резкий"],
        "suggestion": "Добавить переход между постами 2 и 3",
    })

    result = _parse_coherence(raw)
    assert result["score"] == 0.85
    assert len(result["issues"]) == 2
    assert "повторяет" in result["issues"][0]
    assert "переход" in result["suggestion"]


def test_parse_coherence_json_perfect():
    """Parse perfect coherence from JSON."""
    from bot.agents.series_coherence import _parse_coherence

    raw = json.dumps({"score": 1.0, "issues": [], "suggestion": ""})

    result = _parse_coherence(raw)
    assert result["score"] == 1.0
    assert result["issues"] == []
    assert result["suggestion"] == ""


def test_parse_coherence_legacy():
    """Legacy SCORE/ISSUES/SUGGESTION format still works as fallback."""
    from bot.agents.series_coherence import _parse_coherence

    raw = """SCORE: 0.85
ISSUES: Пост 3 повторяет идею из поста 2; Финал слишком резкий
SUGGESTION: Добавить переход между постами 2 и 3"""

    result = _parse_coherence(raw)
    assert result["score"] == 0.85
    assert len(result["issues"]) == 2
    assert "повторяет" in result["issues"][0]
    assert "переход" in result["suggestion"]


def test_parse_coherence_legacy_perfect():
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
    assert "JSON" in result


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
    assert "JSON" in result


def test_coherence_prompt():
    from bot.agents.prompts.series_prompts import coherence_prompt

    result = coherence_prompt("Тест", "Пост 1...\nПост 2...", 2)
    assert "score" in result
    assert "issues" in result


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

    outline_response = json.dumps({
        "summary": "Серия о лаванде",
        "positions": [
            {"index": 1, "title": "Знакомство", "angle": "Первое впечатление", "role": "intro"},
            {"index": 2, "title": "Свойства", "angle": "Deep dive", "role": "middle"},
            {"index": 3, "title": "Итог", "angle": "Завершение", "role": "cta"},
        ],
    })

    writer_response = json.dumps([
        {"index": 1, "caption": "Знаете момент, когда вечером наконец выдыхаешь?", "cta": "Сохрани", "visual_prompt": "lavender field"},
        {"index": 2, "caption": "Лаванда это больше чем запах", "cta": "Попробуй", "visual_prompt": "essential oil"},
        {"index": 3, "caption": "За эту неделю мы узнали о лаванде всё", "cta": "Записаться", "visual_prompt": "person relaxing"},
    ])

    coherence_response = json.dumps({"score": 0.9, "issues": [], "suggestion": ""})

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
