"""Tests for utility functions: message splitting, dash fixing, topic/carousel parsing."""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# _split_message (commands.py)
# ---------------------------------------------------------------------------

from bot.handlers.commands import _split_message
from bot.handlers.content import _topics_text, _source_label


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
from bot.agents.content import (
    _has_structured_content,
    format_content_message,
    make_single_image_prompt,
    make_slide_prompts_no_text,
    make_slide_prompts_with_text,
    parse_content_draft,
    parse_numbered_list,
)


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


class TestAgentParseNumberedList:
    def test_parses_limited_list(self):
        raw = "\n".join(f"{i}. Тема {i}" for i in range(1, 13))
        topics = parse_numbered_list(raw)
        assert len(topics) == 10

    def test_fixes_long_dash(self):
        raw = "1. Тема — про регуляцию"
        topics = parse_numbered_list(raw)
        assert topics == ["Тема - про регуляцию"]


class TestParseContentDraft:
    def test_regular_post_draft(self):
        raw = (
            "ANGLE: Через запах проще заметить, насколько тело перегружено\n"
            "HOOK: Иногда нервная система просит не мотивацию, а паузу\n"
            "CAPTION: Я часто вижу, как аромат возвращает человека в тело быстрее длинных объяснений.\n"
            "CTA: Если хочешь такой формат для себя или команды, напиши мне.\n"
            "HASHTAGS: #ароматерапия #нервнаясистема\n"
            "VISUAL_PROMPT: warm minimalist wellness photo, essential oils, soft daylight"
        )
        draft = parse_content_draft(raw)
        assert "паузу" in draft.hook
        assert draft.slides == []
        assert "essential oils" in draft.visual_prompt

    def test_carousel_draft(self):
        raw = (
            "ANGLE: Сенсорный ритуал как быстрый вход в контакт с собой\n"
            "HOOK: Когда голова шумит, начинай не с мыслей, а с ощущений\n"
            "SLIDE1: Стресс часто начинается с потери контакта с телом\n"
            "SLIDE2: Запах помогает быстрее вернуться в момент\n"
            "SLIDE3: Звук замедляет внутренний темп\n"
            "SLIDE4: Вместе они создают мягкую опору\n"
            "SLIDE5: Такой формат хорошо работает и в личной, и в корпоративной практике\n"
            "CTA: Хочешь попробовать такой опыт - напиши мне\n"
            "HASHTAGS: #гонг #медитация\n"
            "VISUAL_PROMPT: calm sensory ritual, gong, warm neutral palette"
        )
        draft = parse_content_draft(raw)
        assert len(draft.slides) == 5
        assert draft.caption == ""

    def test_multiline_caption_preserved(self):
        raw = (
            "ANGLE: Через тело проще заметить перегрузку\n"
            "HOOK: Иногда лучший шаг - замедлиться\n"
            "CAPTION: Я часто использую запах как мягкий способ вернуться в ощущение себя.\n"
            "Это не магия и не обещание быстрого исцеления.\n"
            "Это конкретный телесный якорь.\n"
            "CTA: Если тебе близок такой подход, напиши мне.\n"
            "HASHTAGS: #сенсорныепрактики\n"
            "VISUAL_PROMPT: quiet ritual, aroma oil, warm light"
        )
        draft = parse_content_draft(raw)
        assert "телесный якорь" in draft.caption

    def test_markdown_labels_are_parsed(self):
        raw = (
            "**ANGLE:** Через тело проще заметить усталость\n"
            "**HOOK:** Иногда лучше не форсировать, а замедлиться\n"
            "**CAPTION:** Аромат может стать мягким якорем внимания.\n"
            "**CTA:** Если хочешь такой формат, напиши мне.\n"
            "**HASHTAGS:** #ароматерапия\n"
            "**VISUAL_PROMPT:** warm ritual, essential oil, calm light"
        )
        draft = parse_content_draft(raw)
        assert "замедлиться" in draft.hook
        assert "#ароматерапия" in draft.hashtags


class TestStructuredContent:
    def test_empty_draft_is_not_structured(self):
        assert _has_structured_content(parse_content_draft("")) is False

    def test_markdown_draft_is_structured(self):
        draft = parse_content_draft("**CAPTION:** Готовый текст")
        assert _has_structured_content(draft) is True


class TestFormatContentMessage:
    def test_formats_carousel(self):
        draft = parse_content_draft(
            "ANGLE: a\nHOOK: b\nSLIDE1: 1\nSLIDE2: 2\nSLIDE3: 3\nSLIDE4: 4\nSLIDE5: 5\nCTA: c\nHASHTAGS: #x\nVISUAL_PROMPT: prompt"
        )
        text = format_content_message(draft, "Тема", "trust", "carousel")
        assert "SLIDES" in text
        assert "TEXT" not in text

    def test_formats_regular_post(self):
        draft = parse_content_draft(
            "ANGLE: a\nHOOK: b\nCAPTION: caption\nCTA: c\nHASHTAGS: #x\nVISUAL_PROMPT: prompt"
        )
        text = format_content_message(draft, "Тема", "sales", "telegram")
        assert "TEXT" in text
        assert "caption" in text


class TestContentTopicsText:
    def test_topics_are_visible_in_message(self):
        text = _topics_text("trust", "telegram", ["Тема 1", "Тема 2"], "trends")
        assert "1. Тема 1" in text
        assert "2. Тема 2" in text
        assert "Доверие" in text
        assert "Актуальные тренды" in text


class TestContentSourceLabel:
    def test_prompt_source_label(self):
        assert _source_label("prompt") == "Свой запрос"


class TestContentImagePrompts:
    def test_with_text_prompts_include_each_slide(self):
        result = make_slide_prompts_with_text("base prompt", ["Слайд один", "Слайд два"])
        assert "Слайд 1:" in result
        assert "Слайд один" in result
        assert "text overlay" in result

    def test_without_text_prompts_preserve_negative_space(self):
        result = make_slide_prompts_no_text("base prompt", ["Слайд один"])
        assert "negative space for text" in result
        assert "no typography" in result

    def test_single_prompt_can_be_built_without_text(self):
        prompt = make_single_image_prompt("base prompt", "Заголовок слайда", with_text=False)
        assert "Заголовок слайда" in prompt
        assert "no typography" in prompt


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

from bot.handlers.carousel import (
    _make_slide_prompts_with_text, _make_slide_prompts_no_text,
    _format_for_canva, _build_pptx,
)

_SLIDES = ["Хук — лаванда снимает стресс", "3 масла для офиса", "Медитация за 15 минут",
           "Корпоративы с ароматерапией", "Запишись сейчас"]
_BASE = "warm minimal photo, essential oils, beige tones"


from bot.agents.carousel_editor import edit_carousel_sync


def _parse_editor_output(raw: str) -> list[str]:
    """Same parsing as edit_carousel_sync but without API call."""
    slides: list[str] = []
    for line in raw.strip().splitlines():
        line = line.strip()
        for i in range(1, 7):
            if line.startswith(f"SLIDE{i}:"):
                slides.append(line.split(":", 1)[1].strip())
                break
    return slides[:6]


class TestCarouselEditor:
    def test_parses_6_slides(self):
        raw = "\n".join(f"SLIDE{i}: Текст слайда {i}" for i in range(1, 7))
        slides = _parse_editor_output(raw)
        assert len(slides) == 6

    def test_ignores_extra_slides(self):
        raw = "\n".join(f"SLIDE{i}: Текст {i}" for i in range(1, 9))
        slides = _parse_editor_output(raw)
        assert len(slides) == 6

    def test_parses_hook_as_first_slide(self):
        raw = "SLIDE1: Хук слайд\nSLIDE2: б\nSLIDE3: в\nSLIDE4: г\nSLIDE5: д\nSLIDE6: CTA"
        slides = _parse_editor_output(raw)
        assert slides[0] == "Хук слайд"
        assert slides[5] == "CTA"

    def test_empty_returns_empty(self):
        assert _parse_editor_output("") == []


class TestBuildPptx:
    _SLIDES = ["Хук", "Слайд 2", "Слайд 3", "Слайд 4", "CTA"]

    def test_returns_bytes(self):
        result = _build_pptx(self._SLIDES)
        assert isinstance(result, bytes)
        assert len(result) > 1000

    def test_pptx_magic_bytes(self):
        # PPTX is a ZIP file — starts with PK
        result = _build_pptx(self._SLIDES)
        assert result[:2] == b"PK"

    def test_with_images(self):
        import struct, zlib
        sig = b"\x89PNG\r\n\x1a\n"
        ihdr = b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
        idat_data = zlib.compress(b"\x00\xff\xff\xff")
        idat = struct.pack(">I", len(idat_data)) + b"IDAT" + idat_data
        idat += struct.pack(">I", zlib.crc32(b"IDAT" + idat_data) & 0xFFFFFFFF)
        iend = b"\x00\x00\x00\x00IEND\xaeB`\x82"
        tiny_png = sig + ihdr + idat + iend
        result = _build_pptx(self._SLIDES, [tiny_png] * 5)
        assert result[:2] == b"PK"
        assert len(result) > 1000

    def test_partial_images(self):
        result = _build_pptx(self._SLIDES, [None, None, None, None, None])
        assert result[:2] == b"PK"


class TestFormatForCanva:
    def test_contains_all_slides(self):
        slides = ["Хук слайд", "Слайд 2", "Слайд 3", "Слайд 4", "CTA слайд"]
        text = _format_for_canva(slides)
        for slide in slides:
            assert slide in text

    def test_has_canva_label(self):
        slides = ["a", "b", "c", "d", "e"]
        text = _format_for_canva(slides)
        assert "Canva" in text

    def test_hook_label_on_first_slide(self):
        slides = ["Хук", "б", "в", "г", "д"]
        text = _format_for_canva(slides)
        assert "Хук" in text

    def test_cta_label_on_last_slide(self):
        slides = ["а", "б", "в", "г", "CTA текст"]
        text = _format_for_canva(slides)
        assert "CTA" in text

    def test_has_nana_banana_hint(self):
        slides = ["а", "б", "в", "г", "д"]
        text = _format_for_canva(slides)
        assert "Nana Banana" in text


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


# ---------------------------------------------------------------------------
# adapter agent — ADAPT_PLATFORM_SPECS / adapt prompt constants
# ---------------------------------------------------------------------------

from bot.agents.adapter import ADAPT_PLATFORM_LABELS, ADAPT_PLATFORM_SPECS


class TestAdapterAgent:
    def test_all_platforms_have_labels(self):
        for key in ["threads", "instagram", "telegram", "reels"]:
            assert key in ADAPT_PLATFORM_LABELS

    def test_all_platforms_have_specs(self):
        for key in ADAPT_PLATFORM_LABELS:
            assert key in ADAPT_PLATFORM_SPECS
            assert len(ADAPT_PLATFORM_SPECS[key]) > 10

    def test_threads_spec_mentions_length(self):
        assert "450" in ADAPT_PLATFORM_SPECS["threads"]

    def test_telegram_spec_longer_than_threads(self):
        # telegram allows longer posts
        assert "1200" in ADAPT_PLATFORM_SPECS["telegram"]


# ---------------------------------------------------------------------------
# reels agent — generate_reels_topics_sync parsing logic
# ---------------------------------------------------------------------------

from bot.agents.reels_agent import generate_reels_topics_sync, generate_reels_scenario_sync


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


# ---------------------------------------------------------------------------
# planner agent — generate_plan_sync format check (structure/constants)
# ---------------------------------------------------------------------------

from bot.agents.planner import _PLAN_PROMPT, _BRAND_CONTEXT


class TestPlannerConstants:
    def test_plan_prompt_has_weekdays(self):
        assert "пн" in _PLAN_PROMPT.lower() or "понедельник" in _PLAN_PROMPT.lower()

    def test_plan_prompt_has_platform_section(self):
        assert "Платформа" in _PLAN_PROMPT

    def test_brand_context_mentions_ароматерапия(self):
        assert "ароматерапия" in _BRAND_CONTEXT.lower() or "сенсорн" in _BRAND_CONTEXT.lower()
