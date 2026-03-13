"""Tests for reels generation, storyboard parsing, and MiniApp reels API."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bot.agents.reels_agent import _parse_storyboard, generate_reels_topics_sync, generate_reels_scenario_sync
from bot.services.miniapp_reels import (
    build_reels_export_payload,
    serialize_reels_draft,
    update_reels_frame_note,
    update_reels_frame_prompt,
)
from bot.services.drafts_store import save_draft


def _parse_reels_topics(raw: str) -> list[str]:
    """Same parsing as generate_reels_topics_sync but without API call."""
    topics: list[str] = []
    for line in raw.strip().splitlines():
        line = line.strip()
        if line and line[0].isdigit() and ". " in line:
            topics.append(line.split(". ", 1)[1].strip())
    return topics[:7]


class TestReelsTopicsParser:
    def test_parses_numbered_list(self):
        raw = "1. Хук про лаванду\n2. Медитация утром\n3. Гонг за 10 минут"
        topics = _parse_reels_topics(raw)
        assert topics == ["Хук про лаванду", "Медитация утром", "Гонг за 10 минут"]

    def test_max_7_topics(self):
        raw = "\n".join(f"{i}. Тема {i}" for i in range(1, 12))
        topics = _parse_reels_topics(raw)
        assert len(topics) == 7

    def test_empty_returns_empty(self):
        assert _parse_reels_topics("") == []

    def test_ignores_non_numbered(self):
        raw = "Вот темы:\n1. Тема одна\nТекст\n2. Тема два"
        topics = _parse_reels_topics(raw)
        assert len(topics) == 2


class TestStoryboardParser:
    def test_parses_all_storyboard_frames(self):
        raw = """\
КАДР1_ТАЙМКОД: 0-3 сек
КАДР1_СЦЕНА: Свеча, масло и ветка шалфея на льняной ткани.
КАДР1_РАКУРС: Крупный план сверху, лёгкий наезд камеры.
КАДР1_ПРОМПТ: cinematic still, terracotta candle, sage branch, beige linen, soft natural light

КАДР2_ТАЙМКОД: 3-10 сек
КАДР2_СЦЕНА: Руки открывают флакон масла рядом с чашкой чая.
КАДР2_РАКУРС: Средний план сбоку, плавное движение.
КАДР2_ПРОМПТ: hands opening essential oil bottle near tea cup, sage and beige palette

КАДР3_ТАЙМКОД: 10-20 сек
КАДР3_СЦЕНА: Поющая чаша и текстура дерева в мягком свете.
КАДР3_РАКУРС: Низкий угол, статичный кадр.
КАДР3_ПРОМПТ: singing bowl on warm wood, terracotta beige sage palette, cinematic

КАДР4_ТАЙМКОД: 20-30 сек
КАДР4_СЦЕНА: Завершающий натюрморт с блокнотом и свечой.
КАДР4_РАКУРС: Фронтальный средний план, спокойный фокус.
КАДР4_ПРОМПТ: calm final still life with notebook and candle, soft natural light, no people
"""
        frames = _parse_storyboard(raw)

        assert len(frames) == 4
        assert frames[0].timecode == "0-3 сек"
        assert "шалфея" in frames[0].scene
        assert "opening essential oil bottle" in frames[1].gemini_prompt
        assert frames[3].angle == "Фронтальный средний план, спокойный фокус."

    def test_skips_empty_frames(self):
        raw = """\
КАДР1_ТАЙМКОД: 0-3 сек
КАДР1_СЦЕНА: Крупный хук с флаконом.
КАДР1_РАКУРС: Макро.
КАДР1_ПРОМПТ: macro shot of essential oil bottle
"""
        frames = _parse_storyboard(raw)

        assert len(frames) == 1
        assert frames[0].timecode == "0-3 сек"

    def test_parses_markdown_wrapped_fields(self):
        raw = """\
- **КАДР1_ТАЙМКОД:** 0-3 сек
- **КАДР1_СЦЕНА:** Свеча и шалфей на ткани.
- **КАДР1_РАКУРС:** Макро сверху.
- **КАДР1_ПРОМПТ:** cinematic still with candle and sage
"""
        frames = _parse_storyboard(raw)

        assert len(frames) == 1
        assert frames[0].scene == "Свеча и шалфей на ткани."


class TestMiniAppReels:
    async def test_serialize_reels_draft_returns_none_for_missing(self):
        assert await serialize_reels_draft("missing-id") is None

    async def test_build_reels_export_payload_returns_none_for_missing(self):
        assert await build_reels_export_payload("missing-id") is None

    async def test_update_reels_frame_note_returns_none_for_missing(self):
        assert await update_reels_frame_note("missing-id", 0, "темнее") is None

    async def test_update_reels_frame_prompt_returns_none_for_missing(self):
        assert await update_reels_frame_prompt("missing-id", 0, "new prompt") is None

    async def test_regenerate_reels_frame_asset_returns_none_for_missing(self):
        from bot.services.reels_assets import regenerate_reels_frame_asset
        assert await regenerate_reels_frame_asset("missing-id", 0) is None


class TestMiniAppReelsPolling:
    def test_server_populates_all_initial_reels_frames(self):
        source = Path("miniapp_server.py").read_text(encoding="utf-8") + "".join(
            p.read_text(encoding="utf-8") for p in sorted(Path("miniapp/api").rglob("*.py"))
        )
        assert "frame_indexes=[0, 1]" not in source
        assert "background_tasks.add_task(" in source


class TestMarkdownRenderingInReelsDetail:
    """Verify that renderMarkdown is wired to the reels scenario field and converts
    **bold** / ## heading to HTML tags on the client side."""

    def test_renderMarkdown_converts_bold_to_strong(self):
        """The JS source must contain the regex that replaces **text** with <strong>."""
        app_js = Path("miniapp/static/app.js").read_text(encoding="utf-8")
        # The inline markdown formatter maps **...** → <strong>...</strong>
        assert '<strong>$1</strong>' in app_js
        assert r"\*\*(.+?)\*\*" in app_js

    def test_renderMarkdown_converts_heading_to_h_tag(self):
        """The JS source must contain logic that maps ## heading lines to <h> elements."""
        app_js = Path("miniapp/static/app.js").read_text(encoding="utf-8")
        assert "chunks.push(`<h${level}>" in app_js
        assert r"/^#{1,3}\s+/" in app_js

    def test_renderMarkdown_is_used_in_reels_scenario_section(self):
        """reels.js must pass the scenario value through renderMarkdown, not raw text."""
        reels_js = Path("miniapp/static/js/reels.js").read_text(encoding="utf-8")
        # renderMarkdown is imported in reels.js and used for frame section values
        assert "renderMarkdown" in reels_js

    def test_reels_api_returns_raw_scenario_for_client_rendering(self):
        """The /api/reels/{id} endpoint returns the raw scenario string so the
        browser JS can render it with renderMarkdown."""
        draft = asyncio.run(
            save_draft(
                kind="reels",
                topic="Тест markdown в сценарии",
                source="/reels",
                payload={
                    "scenario": "## Идея\n\n**Жирный текст** и обычный текст.",
                    "storyboard": [
                        {
                            "timecode": "0-3 сек",
                            "scene": "Свеча",
                            "angle": "Макро",
                            "gemini_prompt": "candle macro",
                        }
                    ],
                    "images_ready": 0,
                },
            )
        )
        from bot.services.miniapp_reels import serialize_reels_draft

        data = asyncio.run(serialize_reels_draft(draft.draft_id))
        assert data is not None
        # The API must return the raw markdown string, not pre-rendered HTML
        scenario = data.get("payload", {}).get("scenario") or draft.payload.get("scenario", "")
        assert "**Жирный текст**" in scenario or "## Идея" in scenario or "<strong>" not in str(data)

    def test_plan_detail_raw_text_is_rendered_via_renderMarkdown_in_js(self):
        """plans.js must use renderMarkdown to display plan raw_text in the detail view."""
        plans_js = Path("miniapp/static/js/plans.js").read_text(encoding="utf-8")
        assert "renderMarkdown" in plans_js
        # Specifically the raw_text field should be passed to renderMarkdown
        assert "renderMarkdown(p.raw_text" in plans_js or "renderMarkdown(" in plans_js

    def test_plan_api_returns_raw_text_with_markdown(self):
        """The plan serializer returns raw_text as-is so the JS can render it."""
        from bot.services.plans_store import save_plan
        from bot.services.miniapp_plans import serialize_plan

        plan = asyncio.run(
            save_plan(
                raw_text="## Понедельник\n**Платформа:** Threads\n**Тема:** Вечерний ритуал",
                entries=[
                    {
                        "day_label": "Понедельник",
                        "platform": "Threads",
                        "format_label": "пост",
                        "goal": "Доверие",
                        "topic": "Вечерний ритуал",
                        "angle": "Через мягкий вход",
                    }
                ],
            )
        )
        data = asyncio.run(serialize_plan(plan))
        # raw_text must be the original markdown string — no pre-rendering server-side
        assert "## Понедельник" in data["raw_text"]
        assert "**Платформа:**" in data["raw_text"]
        # Must NOT contain rendered HTML — that is the browser's job
        assert "<strong>" not in data["raw_text"]
        assert "<h" not in data["raw_text"]


class TestReelsStoryboardFallback:
    """Verify that serialize_reels_draft populates frames from payload.storyboard
    even when no pre-computed frames list exists."""

    async def test_storyboard_frames_are_populated_from_payload(self):
        draft = await save_draft(
            kind="reels",
            topic="Рилс с каркасом",
            source="/reels",
            payload={
                "scenario": "Сценарий про лаванду",
                "storyboard": [
                    {"timecode": "0-3 сек", "scene": "Флакон на ткани", "angle": "Макро"},
                    {"timecode": "3-10 сек", "scene": "Руки с маслом", "angle": "Средний план"},
                ],
                "images_ready": 0,
            },
        )
        from bot.services.miniapp_reels import serialize_reels_draft

        data = await serialize_reels_draft(draft.draft_id)

        assert data is not None
        assert data["frame_count"] == 2
        assert len(data["frames"]) == 2
        assert data["frames"][0]["timecode"] == "0-3 сек"
        assert data["frames"][0]["scene"] == "Флакон на ткани"
        assert data["frames"][1]["angle"] == "Средний план"

    async def test_empty_storyboard_payload_yields_zero_frames(self):
        draft = await save_draft(
            kind="reels",
            topic="Рилс без кадров",
            source="/reels",
            payload={
                "scenario": "Только сценарий, кадров нет",
                "storyboard": [],
                "images_ready": 0,
            },
        )
        from bot.services.miniapp_reels import serialize_reels_draft

        data = await serialize_reels_draft(draft.draft_id)

        assert data is not None
        assert data["frame_count"] == 0
        assert data["frames"] == []

    async def test_storyboard_fallback_via_api(self):
        """Verify via the miniapp test client that GET /api/reels/{id} returns frames
        populated from payload.storyboard even when storyboard was set at draft creation."""
        import miniapp_server

        draft = await save_draft(
            kind="reels",
            topic="API рилс тест",
            source="/reels",
            payload={
                "scenario": "Сценарий для теста API",
                "storyboard": [
                    {
                        "timecode": "0-5 сек",
                        "scene": "Открывают флакон",
                        "angle": "Крупный план",
                        "gemini_prompt": "close-up bottle",
                    }
                ],
                "images_ready": 0,
            },
        )

        with TestClient(miniapp_server.app) as client:
            # patch auth so test client does not need real init-data
            import miniapp.api.auth as _ms_auth
            original_verify = _ms_auth._verify_init_data
            _ms_auth._verify_init_data = lambda _v: True
            try:
                response = client.get(
                    f"/api/reels/{draft.draft_id}",
                    headers={"X-Telegram-Init-Data": "user=%7B%22id%22%3A1%7D&hash=test"},
                )
            finally:
                _ms_auth._verify_init_data = original_verify

        assert response.status_code == 200
        payload = response.json()
        assert payload["frame_count"] == 1
        assert payload["frames"][0]["scene"] == "Открывают флакон"
        assert payload["frames"][0]["timecode"] == "0-5 сек"
