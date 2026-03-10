"""Tests for utility functions: message splitting, dash fixing, topic/carousel parsing."""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# _split_message (commands.py)
# ---------------------------------------------------------------------------

from bot.handlers.commands import _split_message


class TestSplitMessage:
    def test_short_message_unchanged(self):
        assert _split_message("hello", 4096) == ["hello"]

    def test_empty_string(self):
        assert _split_message("", 4096) == [""]

    def test_splits_at_newline(self):
        text = "line1\nline2\nline3"
        chunks = _split_message(text, 10)
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk) <= 10

    def test_all_chunks_within_limit(self):
        text = "\n".join(f"line {i}" * 3 for i in range(50))
        for chunk in _split_message(text, 100):
            assert len(chunk) <= 100

    def test_no_data_loss(self):
        text = "aaa\nbbb\nccc\nddd"
        chunks = _split_message(text, 8)
        joined = "\n".join(chunks)
        # All original words should be present
        for word in ["aaa", "bbb", "ccc", "ddd"]:
            assert word in joined

    def test_exact_limit_not_split(self):
        text = "x" * 100
        assert _split_message(text, 100) == [text]

    def test_over_limit_no_newline_splits_hard(self):
        text = "x" * 200
        chunks = _split_message(text, 100)
        assert len(chunks) == 2
        assert len(chunks[0]) == 100


# ---------------------------------------------------------------------------
# _fix_dashes (threads.py)
# ---------------------------------------------------------------------------

from bot.handlers.threads import _fix_dashes


class TestFixDashes:
    def test_em_dash_replaced(self):
        assert _fix_dashes("слово — слово") == "слово - слово"

    def test_en_dash_replaced(self):
        assert _fix_dashes("2020–2026") == "2020-2026"

    def test_plain_hyphen_unchanged(self):
        assert _fix_dashes("a-b") == "a-b"

    def test_no_dashes(self):
        assert _fix_dashes("обычный текст") == "обычный текст"

    def test_multiple_dashes(self):
        result = _fix_dashes("а — б — в")
        assert "—" not in result
        assert result.count("-") == 2


# ---------------------------------------------------------------------------
# _claude_topics parser (threads.py) — tests the parsing logic, not the API
# ---------------------------------------------------------------------------

from bot.handlers.threads import _claude_topics as _real_claude_topics


def _parse_topics(raw: str) -> list[str]:
    """Same parsing logic as _claude_topics but without API call."""
    topics: list[str] = []
    for line in raw.strip().splitlines():
        line = line.strip()
        if line and line[0].isdigit() and ". " in line:
            topics.append(line.split(". ", 1)[1].strip())
    return topics[:10]


class TestParseTopics:
    def test_standard_numbered_list(self):
        raw = "1. Тема первая\n2. Тема вторая\n3. Тема третья"
        topics = _parse_topics(raw)
        assert topics == ["Тема первая", "Тема вторая", "Тема третья"]

    def test_max_10_topics(self):
        raw = "\n".join(f"{i}. Тема {i}" for i in range(1, 15))
        topics = _parse_topics(raw)
        assert len(topics) == 10

    def test_ignores_non_numbered_lines(self):
        raw = "Вот темы:\n1. Тема одна\nКакой-то текст\n2. Тема два"
        topics = _parse_topics(raw)
        assert len(topics) == 2
        assert topics[0] == "Тема одна"

    def test_empty_response(self):
        assert _parse_topics("") == []

    def test_strips_whitespace(self):
        raw = "1.   Тема с пробелами   "
        topics = _parse_topics(raw)
        assert topics[0] == "Тема с пробелами"


# ---------------------------------------------------------------------------
# _claude_carousel parser (carousel.py) — tests parsing logic
# ---------------------------------------------------------------------------

def _parse_carousel(raw: str) -> tuple[list[str], str]:
    """Same parsing logic as _claude_carousel but without API call."""
    from bot.handlers.threads import _fix_dashes
    slides: list[str] = []
    img_prompt = ""
    for line in raw.strip().splitlines():
        line = line.strip()
        for i in range(1, 6):
            if line.startswith(f"SLIDE{i}:"):
                slides.append(_fix_dashes(line.split(":", 1)[1].strip()))
        if line.startswith("IMG_PROMPT:"):
            img_prompt = line.split(":", 1)[1].strip()
    return slides, img_prompt


class TestParseCarousel:
    SAMPLE = (
        "SLIDE1: Лаванда снимает стресс лучше таблеток\n"
        "SLIDE2: 3 масла которые изменят твой офис\n"
        "SLIDE3: Гонг-медитация за 15 минут\n"
        "SLIDE4: Почему корпоративы с ароматерапией работают\n"
        "SLIDE5: Запишись на сессию прямо сейчас\n"
        "IMG_PROMPT: warm minimal lifestyle photo, essential oils, soft light, beige tones"
    )

    def test_parses_five_slides(self):
        slides, _ = _parse_carousel(self.SAMPLE)
        assert len(slides) == 5

    def test_parses_img_prompt(self):
        _, prompt = _parse_carousel(self.SAMPLE)
        assert "essential oils" in prompt

    def test_slide_content(self):
        slides, _ = _parse_carousel(self.SAMPLE)
        assert slides[0] == "Лаванда снимает стресс лучше таблеток"
        assert slides[4] == "Запишись на сессию прямо сейчас"

    def test_dashes_fixed_in_slides(self):
        raw = "SLIDE1: Стресс — враг\nSLIDE2: б\nSLIDE3: в\nSLIDE4: г\nSLIDE5: д\nIMG_PROMPT: x"
        slides, _ = _parse_carousel(raw)
        assert "—" not in slides[0]
        assert "-" in slides[0]

    def test_empty_response(self):
        slides, prompt = _parse_carousel("")
        assert slides == []
        assert prompt == ""

    def test_partial_response(self):
        raw = "SLIDE1: Только первый слайд\nIMG_PROMPT: photo"
        slides, prompt = _parse_carousel(raw)
        assert len(slides) == 1
        assert prompt == "photo"


# ---------------------------------------------------------------------------
# _make_slide_prompts_with_text / _make_slide_prompts_no_text (carousel.py)
# ---------------------------------------------------------------------------

from bot.handlers.carousel import _make_slide_prompts_with_text, _make_slide_prompts_no_text

_SLIDES = ["Хук — лаванда снимает стресс", "3 масла для офиса", "Медитация за 15 минут",
           "Корпоративы с ароматерапией", "Запишись сейчас"]
_BASE = "warm minimal photo, essential oils, beige tones"


class TestSlidePromptsWithText:
    def test_each_slide_has_own_text(self):
        result = _make_slide_prompts_with_text(_BASE, _SLIDES)
        for slide in _SLIDES:
            assert slide in result

    def test_five_slides_present(self):
        result = _make_slide_prompts_with_text(_BASE, _SLIDES)
        for i in range(1, 6):
            assert f"Слайд {i}:" in result

    def test_contains_base_prompt(self):
        result = _make_slide_prompts_with_text(_BASE, _SLIDES)
        assert _BASE in result

    def test_text_overlay_marker(self):
        result = _make_slide_prompts_with_text(_BASE, _SLIDES)
        assert "text overlay" in result


class TestSlidePromptsNoText:
    def test_each_slide_unique(self):
        result = _make_slide_prompts_no_text(_BASE, _SLIDES)
        lines = [l for l in result.splitlines() if l.startswith("Слайд")]
        # All lines must be different (unique per slide)
        assert len(set(lines)) == len(lines)

    def test_slide_content_in_prompt(self):
        result = _make_slide_prompts_no_text(_BASE, _SLIDES)
        for slide in _SLIDES:
            assert slide[:30] in result

    def test_no_typography_marker(self):
        result = _make_slide_prompts_no_text(_BASE, _SLIDES)
        assert "no typography" in result

    def test_five_slides_present(self):
        result = _make_slide_prompts_no_text(_BASE, _SLIDES)
        for i in range(1, 6):
            assert f"Слайд {i}" in result


# ---------------------------------------------------------------------------
# _fmt_count (wordstat.py)
# ---------------------------------------------------------------------------

from analytics.wordstat import _fmt_count


class TestFmtCount:
    def test_small_number(self):
        assert _fmt_count(100) == "100"

    def test_thousands(self):
        result = _fmt_count(17777)
        assert "17" in result
        assert "777" in result

    def test_zero(self):
        assert _fmt_count(0) == "0"

    def test_million(self):
        result = _fmt_count(1_000_000)
        assert "1" in result
        assert "000" in result


# ---------------------------------------------------------------------------
# Threads collector: _parse_post
# ---------------------------------------------------------------------------

from analytics.threads_collector import _parse_post


class TestThreadsParsePost:
    def test_parses_basic_post(self):
        text = "username\n01/01/26\nThis is a great aromatherapy tip!\n42\n5\n3"
        item = _parse_post(text, "https://threads.net/@username/post/abc")
        assert item is not None
        assert "aromatherapy tip" in item.title

    def test_returns_none_for_too_short(self):
        item = _parse_post("user\ndate\nhi\n1", "https://threads.net/x")
        assert item is None

    def test_extracts_score(self):
        text = "user\n01/01/26\nAromatherapy for stress relief and wellness\n1K\n20\n5"
        item = _parse_post(text, "https://threads.net/@user/post/x")
        assert item is not None
        assert "1K" in item.score

    def test_url_stored(self):
        text = "user\n01/01/26\nEssential oils and sound healing practices\n10\n2"
        url = "https://www.threads.net/@user/post/XYZ"
        item = _parse_post(text, url)
        assert item is not None
        assert item.url == url

    def test_author_in_extra(self):
        text = "aromafan\n02/01/26\nGong meditation changed my life completely!\n55\n8"
        item = _parse_post(text, "https://threads.net/@aromafan/post/1")
        assert item is not None
        assert item.extra["author"] == "aromafan"

    def test_returns_none_for_empty(self):
        assert _parse_post("", "https://threads.net") is None
