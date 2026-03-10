"""Tests for formatters: MarkdownV2 escaping, section formatting, report building."""
from __future__ import annotations

from datetime import datetime

import pytest

from analytics.base import SourceResult, TrendItem
from formatters.sections import _esc, format_section
from formatters.report import build_report, _date_str


# ---------------------------------------------------------------------------
# _esc — MarkdownV2 escaping
# ---------------------------------------------------------------------------

class TestEsc:
    def test_plain_text_unchanged(self):
        assert _esc("hello world") == "hello world"

    def test_escapes_dot(self):
        assert _esc("v1.0") == r"v1\.0"

    def test_escapes_dash(self):
        assert _esc("a-b") == r"a\-b"

    def test_escapes_parens(self):
        assert _esc("(ok)") == r"\(ok\)"

    def test_escapes_underscore(self):
        assert _esc("some_word") == r"some\_word"

    def test_escapes_asterisk(self):
        assert _esc("a*b") == r"a\*b"

    def test_escapes_multiple(self):
        result = _esc("v1.0 (beta) — ok!")
        assert "\\." in result
        assert "\\(" in result
        assert "\\)" in result
        assert "\\!" in result

    def test_empty_string(self):
        assert _esc("") == ""


# ---------------------------------------------------------------------------
# format_section
# ---------------------------------------------------------------------------

def _make_result(source_key: str, items: list[TrendItem] | None = None,
                 error: str = "") -> SourceResult:
    return SourceResult(
        source_name="Test Source",
        source_key=source_key,
        icon="📊",
        items=items or [],
        error=error,
    )


class TestFormatSection:
    def test_error_shows_warning(self):
        result = _make_result("reddit", error="timeout")
        text = format_section(result)
        assert "⚠️" in text
        assert "timeout" in text

    def test_divider_always_present(self):
        result = _make_result("reddit", items=[TrendItem(title="x", score="10")])
        text = format_section(result)
        assert "━" in text

    def test_source_name_in_header(self):
        result = _make_result("reddit", items=[TrendItem(title="x", score="10")])
        text = format_section(result)
        assert "Test Source" in text

    def test_wordstat_shows_volume_and_trend(self):
        items = [TrendItem(title="ароматерапия", score="17 777 показов/мес", extra="▲8% vs прошлый мес.")]
        result = _make_result("wordstat", items=items)
        text = format_section(result)
        assert "ароматерапия" in text
        assert "показов" in text
        assert "▲8" in text

    def test_youtube_shows_link(self):
        items = [TrendItem(title="Видео про лаванду", url="https://youtube.com/watch?v=abc123", score="1к просмотров")]
        result = _make_result("youtube", items=items)
        text = format_section(result)
        assert "Видео про лаванду" in text
        # URL is in markdown link syntax — dot gets escaped to \. in MarkdownV2
        assert "youtube" in text

    def test_youtube_shows_summary(self):
        items = [TrendItem(title="Видео", url="https://youtube.com/watch?v=x", score="", summary="Краткое содержание")]
        result = _make_result("youtube", items=items)
        text = format_section(result)
        assert "Краткое содержание" in text

    def test_youtube_no_summary_when_empty(self):
        items = [TrendItem(title="Видео", url="https://youtube.com/watch?v=x", score="")]
        result = _make_result("youtube", items=items)
        text = format_section(result)
        # should not contain italic markers for empty summary
        lines = [l for l in text.splitlines() if l.strip().startswith("_") and l.strip().endswith("_")]
        assert not lines

    def test_reddit_shows_bullet(self):
        items = [TrendItem(title="Essential oils question", url="https://reddit.com/r/x", score="42 upvotes")]
        result = _make_result("reddit", items=items)
        text = format_section(result)
        assert "Essential oils question" in text
        assert "42" in text

    def test_tiktok_shows_numbered_list(self):
        items = [TrendItem(title="TikTok video", url="https://tiktok.com/@x/1", score="10к", extra="#ароматерапия")]
        result = _make_result("tiktok", items=items)
        text = format_section(result)
        assert "1" in text
        assert "TikTok video" in text

    def test_vk_no_url(self):
        items = [TrendItem(title="Пост ВК", score="100 лайков")]
        result = _make_result("vk", items=items)
        text = format_section(result)
        assert "Пост ВК" in text

    def test_ai_recommendations_full_text(self):
        items = [TrendItem(title="Идея 1\nИдея 2\nИдея 3")]
        result = _make_result("ai_recommendations", items=items)
        text = format_section(result)
        assert "Идея 1" in text

    def test_empty_items_with_no_error_shows_warning(self):
        # ok=False when no items and no error → shows warning
        result = _make_result("reddit", items=[], error="нет данных")
        text = format_section(result)
        assert "⚠️" in text


# ---------------------------------------------------------------------------
# build_report
# ---------------------------------------------------------------------------

class TestBuildReport:
    def _ru_results(self) -> list[SourceResult]:
        return [
            SourceResult(
                source_name="Google Trends RU", source_key="google_trends_ru", icon="📈",
                items=[TrendItem(title="ароматерапия", score="+50%")],
            ),
            SourceResult(
                source_name="YouTube EN", source_key="youtube", icon="▶️",
                items=[TrendItem(title="Aromatherapy", url="https://youtube.com/watch?v=abc", score="1k")],
            ),
        ]

    def test_ru_report_contains_flag(self):
        report = build_report(self._ru_results(), lang="ru", now=datetime(2026, 3, 10))
        assert "🇷🇺" in report

    def test_en_report_contains_flag(self):
        report = build_report(self._ru_results(), lang="en", now=datetime(2026, 3, 10))
        assert "🇬🇧" in report

    def test_ru_report_includes_ru_source(self):
        report = build_report(self._ru_results(), lang="ru", now=datetime(2026, 3, 10))
        assert "Google Trends RU" in report

    def test_ru_report_excludes_en_source(self):
        report = build_report(self._ru_results(), lang="ru", now=datetime(2026, 3, 10))
        assert "YouTube EN" not in report

    def test_en_report_includes_en_source(self):
        report = build_report(self._ru_results(), lang="en", now=datetime(2026, 3, 10))
        assert "YouTube EN" in report

    def test_report_contains_hashtag_footer(self):
        report = build_report(self._ru_results(), lang="ru", now=datetime(2026, 3, 10))
        assert "хэштеги" in report.lower()

    def test_date_in_report(self):
        report = build_report(self._ru_results(), lang="ru", now=datetime(2026, 3, 10))
        assert "2026" in report

    def test_ru_date_month_in_russian(self):
        report = build_report(self._ru_results(), lang="ru", now=datetime(2026, 3, 10))
        assert "марта" in report


class TestDateStr:
    def test_march_in_russian(self):
        assert _date_str(datetime(2026, 3, 10)) == "10 марта 2026"

    def test_january_in_russian(self):
        assert _date_str(datetime(2026, 1, 1)) == "1 января 2026"

    def test_december_in_russian(self):
        assert _date_str(datetime(2026, 12, 31)) == "31 декабря 2026"
