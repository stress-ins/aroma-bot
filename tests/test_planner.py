"""Tests for planner constants, plan entry parsing, and threads prompt structure."""
from __future__ import annotations

from pathlib import Path

import pytest

from bot.agents.planner import _PLAN_PROMPT, _BRAND_CONTEXT
from bot.handlers.planner import _parse_plan_entries


class TestPlannerConstants:
    def test_plan_prompt_has_weekdays(self):
        assert "пн" in _PLAN_PROMPT.lower() or "понедельник" in _PLAN_PROMPT.lower()

    def test_plan_prompt_has_platform_section(self):
        assert "Платформа" in _PLAN_PROMPT

    def test_brand_context_mentions_ароматерапия(self):
        assert "ароматерапия" in _BRAND_CONTEXT.lower() or "сенсорн" in _BRAND_CONTEXT.lower()


class TestPlanParser:
    def test_parses_three_plan_entries(self):
        raw = """\
📅 Понедельник
Платформа: Threads
Формат: пост
Цель: Доверие
Тема: Почему запахи помогают замедлиться вечером.
Угол: Через знакомую офисную перегрузку.

📅 Среда
Платформа: Instagram
Формат: карусель
Цель: Экспертность
Тема: Как мягко вернуть тело в состояние опоры.
Угол: Разобрать 3 сенсорных якоря.

📅 Пятница
Платформа: Reels
Формат: рилс
Цель: Вовлечение
Тема: Вечерний ритуал на 30 секунд.
Угол: Быстрая практика перед сном.
"""
        entries = _parse_plan_entries(raw)

        assert len(entries) == 3
        assert entries[0].platform == "Threads"
        assert entries[1].format_label == "карусель"
        assert entries[2].topic == "Вечерний ритуал на 30 секунд."


class TestThreadsPrompts:
    def test_writer_rules_for_threads_define_three_daily_posts(self):
        from bot.agents.content import _PLATFORM_RULES_WRITER

        rules = _PLATFORM_RULES_WRITER["threads"]
        assert "morning, day, evening" in rules
        assert "5-12 short lines" in rules
        assert "40-120 words" in rules
        assert "no hashtags" in rules

    def test_legacy_threads_prompt_uses_new_daily_pack_format(self):
        from bot.handlers.threads import _PROMPT_POST

        prompt = _PROMPT_POST
        assert "3 поста для Threads на сегодня" in prompt
        assert "УТРО, ДЕНЬ, ВЕЧЕР" in prompt

    def test_writer_prompt_demands_plain_human_rhythm(self):
        from bot.agents.content import _writer_prompt

        prompt = _writer_prompt("тема", "trust", "telegram", "угол", "хук")
        lowered = prompt.lower()
        assert "живой человек" in lowered
        assert "без резких обрывов" in lowered
        assert "если фраза звучит как слоган" in lowered

    def test_client_waits_for_all_reels_frames(self):
        source = " ".join(p.read_text(encoding="utf-8") for p in sorted(Path("miniapp/static").rglob("*.js")))
        assert "readyFrames < (reel.frame_count || 0)" in source

    def test_bootstrap_does_not_block_first_render_on_reference_access(self):
        source = " ".join(p.read_text(encoding="utf-8") for p in sorted(Path("miniapp/static").rglob("*.js")))
        # Extract only the runtime bootstrap function body (the actual implementation, not the wrapper)
        bootstrap_section = source.split("async function bootstrap() {\n    applyTelegramTheme();", 1)[1].split("function retryCurrentTab()", 1)[0]

        assert 'if (state.mode === "content") {' in source
        assert "void loadReferenceAccess();" in source
        assert "await loadReferenceAccess();" not in bootstrap_section
        assert 'throw new Error("request_timeout")' in source
        assert 'new Promise((resolve) => {' in source
        assert 'showBootFallback(' in source

    def test_startup_errors_keep_boot_fallback_visible_until_first_render(self):
        core_js = Path("miniapp/static/js/core.js").read_text(encoding="utf-8")
        runtime_warning = core_js.split("function showRuntimeWarning(prefix, error) {", 1)[1].split("async function copyText", 1)[0]

        assert 'if (!callbacks.isBootstrapped()) {' in runtime_warning
        assert 'showBootFallback(prefix, humanMessage, true);' in runtime_warning
        assert 'hideBootFallback();' in runtime_warning

    def test_reference_access_timeout_stays_retriable(self):
        source = " ".join(p.read_text(encoding="utf-8") for p in sorted(Path("miniapp/static").rglob("*.js")))

        assert "referenceAccessError" in source
        assert 'state.referenceAccess = null;' in source
        assert "renderReferencesUnavailable()" in source
        assert "reference_access_denied" in source

    def test_index_disables_html_cache_and_bumps_static_version(self):
        index_html = Path("miniapp/index.html").read_text(encoding="utf-8")
        server_py = Path("miniapp_server.py").read_text(encoding="utf-8") + "".join(
            p.read_text(encoding="utf-8") for p in sorted(Path("miniapp/api").rglob("*.py"))
        )

        assert "app.css?v=4" in index_html or "app.css?v=__ASSET_VERSION__" in index_html
        assert "app.js?v=4" in index_html or "app.js?v=__ASSET_VERSION__" in index_html
        assert "Cache-Control" in server_py
        assert "no-store, max-age=0" in server_py

    def test_background_refresh_does_not_reroute_handbook_view(self):
        source = " ".join(p.read_text(encoding="utf-8") for p in sorted(Path("miniapp/static").rglob("*.js")))

        assert "function clearBackgroundRefreshes" in source
        assert "function isCurrentDraftDetail" in source
        assert "function isCurrentReelsDetail" in source
        assert "if (isCurrentDraftDetail(draft.draft_id)) {" in source
        assert "if (isCurrentReelsDetail(reel.draft_id)) {" in source
        assert "clearBackgroundRefreshes();" in source.split("function setMode", 1)[1]
        assert "clearBackgroundRefreshes();" in source.split("function setTab", 1)[1]

    def test_create_flows_route_into_detail_cards(self):
        source = " ".join(p.read_text(encoding="utf-8") for p in sorted(Path("miniapp/static").rglob("*.js")))

        assert "function draftSummaryFromDraft(draft) {" in source
        assert "function upsertDraftSummary(summary) {" in source
        assert 'openPendingDraftCreation(format, topic)' in source
        assert 'const pending = openPendingDraftCreation("carousel", topic);' in source
        assert "function finalizePendingDraftCreation(draft) {" in source
        assert 'upsertDraftSummary(draftSummaryFromDraft(draft));' in source
        assert 'renderDraftDetail(draft);' in source
        assert 'await recoverPendingDraftCreation("carousel", topic, pending.draft_id);' in source
        assert 'state.selectedReels = reel;' in source
        assert 'scheduleReelsRefresh(reel.draft_id);' in source
        assert 'state.selectedPlan = p;' in source
        assert 'setTab("plans");' in source
        assert 'await loadPlans();' in source
        assert 'renderPlanDetail(p);' in source
        assert "async function openReels(id) {" in source
        assert "async function openPlan(id) {" in source
        assert "window.openReels = openReels;" in source
        assert "window.openPlan = openPlan;" in source

    def test_load_drafts_keeps_list_alive_if_detail_open_fails(self):
        source = " ".join(p.read_text(encoding="utf-8") for p in sorted(Path("miniapp/static").rglob("*.js")))

        assert 'const data = await fetchJson(`/api/drafts?${filtersToQueryString()}`, { timeout: 20000 });' in source
        assert 'await openDraft(preferredId);' in source
        assert 'console.error("miniapp failed to open preferred draft", error);' in source
        assert 'renderDetailError("Не удалось открыть карточку", message, `openDraft(\'${preferredId}\')`)' in source
