"""Tests: content format validation — markdown stripping and format audit."""
from __future__ import annotations

import pytest


class TestStripMarkdownFormatting:
    def test_strips_headers(self):
        from bot.agents.content import _strip_markdown_formatting
        assert _strip_markdown_formatting("# Заголовок\nТекст") == "Заголовок\nТекст"
        assert _strip_markdown_formatting("## Подзаголовок\n### Третий") == "Подзаголовок\nТретий"

    def test_strips_bold_italic(self):
        from bot.agents.content import _strip_markdown_formatting
        assert _strip_markdown_formatting("**жирный** и *курсив*") == "жирный и курсив"
        assert _strip_markdown_formatting("__жирный__ и _курсив_") == "жирный и курсив"

    def test_strips_blockquotes(self):
        from bot.agents.content import _strip_markdown_formatting
        assert _strip_markdown_formatting("> цитата\nтекст") == "цитата\nтекст"

    def test_strips_code_fences(self):
        from bot.agents.content import _strip_markdown_formatting
        assert _strip_markdown_formatting("до\n```\nкод\n```\nпосле") == "до\n\nпосле"

    def test_preserves_plain_text(self):
        from bot.agents.content import _strip_markdown_formatting
        text = "Простой текст без разметки.\nВторая строка."
        assert _strip_markdown_formatting(text) == text


class TestFormatAudit:
    def test_detects_analysis_content(self):
        from bot.agents.quality_evaluator import _format_audit
        scores = {"coherence": 0.8, "brand_fit": 0.8, "hook_strength": 0.8,
                  "cta_clarity": 0.7, "humanness": 0.8, "critique": "", "overall": 0.8, "passed": True}
        text = "# Разбор текста\nВы показали пример **эмоционального копирайтинга**.\n## Что здесь сильного:"
        result = _format_audit(scores, text, "threads_series")
        assert result["coherence"] <= 0.3
        assert result["brand_fit"] <= 0.3
        assert not result["passed"]
        assert "analysis" in result["critique"].lower()

    def test_detects_markdown_formatting(self):
        from bot.agents.quality_evaluator import _format_audit
        scores = {"coherence": 0.8, "brand_fit": 0.8, "hook_strength": 0.8,
                  "cta_clarity": 0.7, "humanness": 0.8, "critique": "", "overall": 0.8, "passed": True}
        text = "# Заголовок\n**Жирный текст** и ещё **один**\nОбычный текст"
        result = _format_audit(scores, text, "threads_series")
        assert result["humanness"] <= 0.4
        assert "Markdown" in result["critique"]

    def test_passes_clean_post(self):
        from bot.agents.quality_evaluator import _format_audit
        scores = {"coherence": 0.8, "brand_fit": 0.8, "hook_strength": 0.8,
                  "cta_clarity": 0.7, "humanness": 0.8, "critique": "", "overall": 0.78, "passed": True}
        text = "Знаешь, что самое странное?\nКогда устал, но не можешь уснуть.\nТело просит отдыха, голова не даёт."
        result = _format_audit(scores, text, "threads_series")
        assert result["passed"]
        assert result["overall"] == 0.78  # unchanged

    def test_telegram_allows_bold(self):
        from bot.agents.quality_evaluator import _format_audit
        scores = {"coherence": 0.8, "brand_fit": 0.8, "hook_strength": 0.8,
                  "cta_clarity": 0.7, "humanness": 0.8, "critique": "", "overall": 0.78, "passed": True}
        text = "**Важная мысль** и ещё **одна**\nОбычный текст"
        result = _format_audit(scores, text, "telegram")
        assert result["humanness"] == 0.8  # telegram allows markdown bold
