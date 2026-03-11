"""Tests for utility functions: message splitting, dash fixing, topic/carousel parsing."""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# _split_message (commands.py)
# ---------------------------------------------------------------------------

from bot.handlers.commands import _split_message
from bot.handlers.content import _topics_text, _source_label
from bot.agents.threads_replies import _extract_json


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


class TestThreadsReplyJson:
    def test_extracts_json_array(self):
        raw = 'before\n[{"candidate_index":1,"reason":"ok","draft_reply":"reply"}]\nafter'
        payload = _extract_json(raw)
        assert payload[0]["candidate_index"] == 1

    def test_invalid_json_returns_empty(self):
        assert _extract_json("not json") == []


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
    _SLIDE_VISUAL_ROLES, _generate_slide_image_prompts_sync,
    _embed_font_in_pptx, _FONT_NAME,
)

_SLIDES = ["Хук — лаванда снимает стресс", "3 масла для офиса", "Медитация за 15 минут",
           "Корпоративы с ароматерапией", "Запишись сейчас"]

# Per-slide image prompts fixture — each one is unique
_IMG_PROMPTS = [
    "dried lavender bundle on terracotta tile, close-up, soft morning light, --ar 1:1 --style atmospheric",
    "sage green desk with small diffuser, essential oils in glass bottles, office minimal, --ar 1:1 --style atmospheric",
    "woman's hands resting on knees near lit candle, beige linen background, --ar 1:1 --style atmospheric",
    "stones and dried herbs arranged on wood surface, warm amber light, abstract, --ar 1:1 --style atmospheric",
    "two hands cupped around a small smooth stone, close-up, terracotta ground, --ar 1:1 --style atmospheric",
]


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

    def test_font_embedded(self):
        import zipfile, io
        result = _build_pptx(self._SLIDES)
        with zipfile.ZipFile(io.BytesIO(result)) as z:
            assert "ppt/fonts/font1.ttf" in z.namelist()
            pxml = z.read("ppt/presentation.xml").decode()
            assert "embeddedFontLst" in pxml
            assert _FONT_NAME in pxml
            rels = z.read("ppt/_rels/presentation.xml.rels").decode()
            assert "font" in rels
            ct = z.read("[Content_Types].xml").decode()
            assert "x-fontdata" in ct

    def test_font_name_in_slide_xml(self):
        import zipfile, io
        result = _build_pptx(self._SLIDES)
        with zipfile.ZipFile(io.BytesIO(result)) as z:
            # Find at least one slide and verify font name
            slide_files = [n for n in z.namelist() if n.startswith("ppt/slides/slide")]
            assert slide_files, "No slide files found"
            slide_xml = z.read(slide_files[0]).decode()
            assert _FONT_NAME in slide_xml

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
        result = _make_slide_prompts_with_text(_IMG_PROMPTS, _SLIDES)
        for slide in _SLIDES:
            assert slide in result

    def test_five_slides_present(self):
        result = _make_slide_prompts_with_text(_IMG_PROMPTS, _SLIDES)
        for i in range(1, 6):
            assert f"Слайд {i}:" in result

    def test_text_overlay_injected(self):
        result = _make_slide_prompts_with_text(_IMG_PROMPTS, _SLIDES)
        assert "text overlay" in result

    def test_each_prompt_is_unique(self):
        result = _make_slide_prompts_with_text(_IMG_PROMPTS, _SLIDES)
        # Extract <pre>...</pre> blocks — each must be different
        import re
        blocks = re.findall(r"<pre>(.*?)</pre>", result, re.DOTALL)
        assert len(blocks) == len(_SLIDES)
        assert len(set(blocks)) == len(blocks)

    def test_per_slide_base_prompt_used(self):
        import html as _html
        # A distinctive word from each base prompt must appear in the result (unescape HTML entities)
        result = _html.unescape(_make_slide_prompts_with_text(_IMG_PROMPTS, _SLIDES))
        for prompt in _IMG_PROMPTS:
            fragment = prompt.split(",")[0][:20]
            assert fragment in result


class TestSlidePromptsNoText:
    def test_each_slide_label_present(self):
        result = _make_slide_prompts_no_text(_IMG_PROMPTS, _SLIDES)
        for i in range(1, 6):
            assert f"Слайд {i}" in result

    def test_slide_text_shown_in_header(self):
        result = _make_slide_prompts_no_text(_IMG_PROMPTS, _SLIDES)
        for slide in _SLIDES:
            assert slide[:30] in result

    def test_each_prompt_is_unique(self):
        result = _make_slide_prompts_no_text(_IMG_PROMPTS, _SLIDES)
        import re
        blocks = re.findall(r"<pre>(.*?)</pre>", result, re.DOTALL)
        assert len(blocks) == len(_SLIDES)
        assert len(set(blocks)) == len(blocks)

    def test_per_slide_prompt_content_present(self):
        import html as _html
        result = _html.unescape(_make_slide_prompts_no_text(_IMG_PROMPTS, _SLIDES))
        for prompt in _IMG_PROMPTS:
            fragment = prompt.split(",")[0][:20]
            assert fragment in result


# ---------------------------------------------------------------------------
# _SLIDE_VISUAL_ROLES + _generate_slide_image_prompts_sync (carousel.py)
# ---------------------------------------------------------------------------

class TestSlideVisualRoles:
    def test_has_six_roles(self):
        assert len(_SLIDE_VISUAL_ROLES) == 6

    def test_roles_are_distinct(self):
        assert len(set(_SLIDE_VISUAL_ROLES)) == 6

    def test_hook_is_first(self):
        assert "hook" in _SLIDE_VISUAL_ROLES[0].lower()

    def test_cta_is_last(self):
        last = _SLIDE_VISUAL_ROLES[-1].lower()
        assert "call" in last or "action" in last or "invitation" in last


class TestGenerateSlideImagePrompts:
    """Tests for _generate_slide_image_prompts_sync — mocks Claude API."""

    _SLIDES_6 = ["Хук", "Проблема", "Механизм", "Инсайт", "Решение", "CTA"]

    def _make_fake_client(self, response_text: str):
        class _FakeClient:
            def __init__(self, **kw): pass
            class messages:
                @staticmethod
                def create(*a, **kw):
                    class _R:
                        content = [type("c", (), {"text": response_text})()]
                    return _R()
        return _FakeClient

    def test_returns_same_count_as_slides(self, monkeypatch):
        import bot.handlers.carousel as c
        import anthropic as _anthropic
        response = "\n".join(
            f"IMG{i + 1}: unique visual {i + 1}, terracotta, --ar 1:1 --style atmospheric"
            for i in range(len(self._SLIDES_6))
        )
        monkeypatch.setattr(c, "settings", type("s", (), {"anthropic_api_key": "x"})())
        monkeypatch.setattr(_anthropic, "Anthropic", lambda **kw: self._make_fake_client(response)())
        result = c._generate_slide_image_prompts_sync(self._SLIDES_6, "тема")
        assert len(result) == len(self._SLIDES_6)

    def test_prompts_are_unique(self, monkeypatch):
        import bot.handlers.carousel as c
        import anthropic as _anthropic
        response = "\n".join(
            f"IMG{i + 1}: scene_{i + 1} with object_{i + 1}, beige, --ar 1:1 --style atmospheric"
            for i in range(len(self._SLIDES_6))
        )
        monkeypatch.setattr(c, "settings", type("s", (), {"anthropic_api_key": "x"})())
        monkeypatch.setattr(_anthropic, "Anthropic", lambda **kw: self._make_fake_client(response)())
        result = c._generate_slide_image_prompts_sync(self._SLIDES_6, "тема")
        assert len(set(result)) == len(result)

    def test_fallback_on_empty_parse(self, monkeypatch):
        """If Claude response is unparseable, fallback strings are returned."""
        import bot.handlers.carousel as c
        import anthropic as _anthropic
        monkeypatch.setattr(c, "settings", type("s", (), {"anthropic_api_key": "x"})())
        monkeypatch.setattr(_anthropic, "Anthropic", lambda **kw: self._make_fake_client("ничего")())
        slides = ["А", "Б"]
        result = c._generate_slide_image_prompts_sync(slides, "тема")
        assert len(result) == 2
        assert all(isinstance(p, str) and len(p) > 10 for p in result)

    def test_each_result_contains_style_flag(self, monkeypatch):
        """Every returned prompt must end with the standard style flag."""
        import bot.handlers.carousel as c
        import anthropic as _anthropic
        response = "\n".join(
            f"IMG{i + 1}: visual {i + 1}, terracotta, --ar 1:1 --style atmospheric"
            for i in range(len(self._SLIDES_6))
        )
        monkeypatch.setattr(c, "settings", type("s", (), {"anthropic_api_key": "x"})())
        monkeypatch.setattr(_anthropic, "Anthropic", lambda **kw: self._make_fake_client(response)())
        result = c._generate_slide_image_prompts_sync(self._SLIDES_6, "тема")
        for p in result:
            assert "--style atmospheric" in p


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

from bot.agents.reels_agent import _parse_storyboard, generate_reels_topics_sync, generate_reels_scenario_sync


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


# ---------------------------------------------------------------------------
# planner agent — generate_plan_sync format check (structure/constants)
# ---------------------------------------------------------------------------

from bot.agents.planner import _PLAN_PROMPT, _BRAND_CONTEXT
from bot.handlers.planner import _parse_plan_entries
from bot.services.drafts_store import DraftRecord
from bot.services.miniapp_presenter import filter_drafts, payload_preview, serialize_draft
from bot.services.miniapp_keywords import field_labels, serialize_topics
from bot.services.miniapp_plans import serialize_plan
from bot.services.miniapp_reels import serialize_reels_draft, update_reels_frame_note
from bot.services.plans_store import PlanRecord


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


class TestDraftRecord:
    def test_draft_record_keeps_fields(self):
        record = DraftRecord(
            draft_id="abc12345",
            kind="reels",
            topic="Вечерний ритуал",
            source="/reels",
            created_at="2026-03-11T07:00:00+00:00",
            status="draft",
            feedback="",
            payload={"scenario": "test"},
        )

        assert record.kind == "reels"
        assert record.source == "/reels"
        assert record.status == "draft"
        assert record.payload["scenario"] == "test"

    def test_draft_record_can_store_approved_status(self):
        record = DraftRecord(
            draft_id="approved1",
            kind="threads",
            topic="Тест",
            source="/content",
            created_at="2026-03-11T07:00:00+00:00",
            status="approved",
            feedback="worked",
            payload={"caption": "ok"},
        )

        assert record.status == "approved"
        assert record.feedback == "worked"


class TestMiniAppPresenter:
    def test_filter_drafts_by_kind_status_and_query(self):
        drafts = [
            DraftRecord(
                draft_id="aaa11111",
                kind="reels",
                topic="Вечерний ритуал",
                source="/reels",
                created_at="2026-03-11T07:00:00+00:00",
                status="approved",
                feedback="worked",
                payload={"scenario": "script"},
            ),
            DraftRecord(
                draft_id="bbb22222",
                kind="threads",
                topic="Утренний якорь",
                source="/content",
                created_at="2026-03-11T08:00:00+00:00",
                status="draft",
                feedback="",
                payload={"caption": "caption"},
            ),
        ]

        result = filter_drafts(
            drafts,
            kind="reels",
            status="approved",
            feedback="worked",
            query="ритуал",
        )

        assert len(result) == 1
        assert result[0].draft_id == "aaa11111"

    def test_payload_preview_prefers_reels_scenario(self):
        preview = payload_preview("reels", {"scenario": "Сценарий с таймкодами"})
        assert "таймкодами" in preview

    def test_payload_preview_uses_slides_for_carousel(self):
        preview = payload_preview("carousel", {"slides": ["Слайд 1", "Слайд 2", "Слайд 3"]})
        assert "Слайд 1" in preview
        assert "Слайд 2" in preview

    def test_serialize_draft_counts_storyboard_frames(self):
        draft = DraftRecord(
            draft_id="ccc33333",
            kind="reels",
            topic="Тёплый вечерний ролик",
            source="/reels",
            created_at="2026-03-11T09:00:00+00:00",
            status="in_review",
            feedback="",
            payload={
                "scenario": "text",
                "storyboard": [
                    {"timecode": "0-3"},
                    {"timecode": "3-10"},
                    {"timecode": "10-20"},
                ],
            },
        )

        data = serialize_draft(draft)

        assert data["storyboard_count"] == 3
        assert data["slides_count"] == 0
        assert data["preview"] == "text"


class TestMiniAppKeywords:
    def test_field_labels_exposes_ru_and_en_fields(self):
        labels = field_labels()
        assert "kw_ru" in labels
        assert "tag_en" in labels

    def test_serialize_topics_returns_named_topics(self):
        topics = serialize_topics()
        assert len(topics) >= 1
        assert "name" in topics[0]
        assert "fields" in topics[0]


class TestMiniAppPlans:
    def test_serialize_plan_keeps_entries(self):
        plan = PlanRecord(
            plan_id="20260311120000",
            created_at="2026-03-11T12:00:00+00:00",
            raw_text="📅 Понедельник\nПлатформа: Threads",
            entries=[
                {
                    "day_label": "Понедельник",
                    "platform": "Threads",
                    "format_label": "пост",
                    "goal": "Доверие",
                    "topic": "Почему запахи помогают замедлиться вечером.",
                    "angle": "Через офисную перегрузку.",
                }
            ],
        )

        data = serialize_plan(plan)

        assert data["plan_id"] == "20260311120000"
        assert len(data["entries"]) == 1
        assert data["entries"][0]["platform"] == "Threads"


class TestMiniAppReels:
    def test_serialize_reels_draft_returns_none_for_missing(self):
        assert serialize_reels_draft("missing-id") is None

    def test_update_reels_frame_note_returns_none_for_missing(self):
        assert update_reels_frame_note("missing-id", 0, "темнее") is None


# ---------------------------------------------------------------------------
# creative_team — edit_post_sync (unit: prompt structure + fallback logic)
# ---------------------------------------------------------------------------

from bot.agents.creative_team import _PLATFORM_RULES, _EDITOR_SYSTEM, edit_post_sync


class TestCreativeTeamConstants:
    def test_platform_rules_has_threads(self):
        assert "threads" in _PLATFORM_RULES
        assert "450" in _PLATFORM_RULES["threads"]

    def test_platform_rules_has_instagram(self):
        assert "instagram" in _PLATFORM_RULES
        assert "900" in _PLATFORM_RULES["instagram"]

    def test_platform_rules_has_telegram(self):
        assert "telegram" in _PLATFORM_RULES

    def test_platform_rules_has_default(self):
        assert "default" in _PLATFORM_RULES

    def test_editor_system_mentions_hook(self):
        assert "хук" in _EDITOR_SYSTEM.lower() or "hook" in _EDITOR_SYSTEM.lower() or "скролл" in _EDITOR_SYSTEM.lower()

    def test_editor_system_forbids_stampы(self):
        # Must mention at least one banned cliché
        assert "позволь себе" in _EDITOR_SYSTEM or "погружаясь" in _EDITOR_SYSTEM

    def test_editor_system_mentions_cta(self):
        assert "cta" in _EDITOR_SYSTEM.lower() or "призыв" in _EDITOR_SYSTEM.lower() or "CTA" in _EDITOR_SYSTEM


class TestEditPostFallback:
    """edit_post_sync must fall back to the original if result is too short."""

    def test_fallback_on_short_result(self, monkeypatch):
        """If Claude returns a very short string, keep original."""
        import bot.agents.creative_team as ct

        def _fake_call(*args, **kwargs):
            class _FakeResp:
                content = [type("c", (), {"text": "ok"})()]
            return _FakeResp()

        class _FakeClient:
            def __init__(self, *a, **kw): pass
            class messages:
                @staticmethod
                def create(*a, **kw):
                    class _R:
                        content = [type("c", (), {"text": "ok"})()]
                    return _R()

        monkeypatch.setattr(ct, "settings", type("s", (), {"anthropic_api_key": "x"})())
        import anthropic as _anthropic
        monkeypatch.setattr(_anthropic, "Anthropic", lambda **kw: _FakeClient())

        original = "Это нормальный пост с достаточным количеством символов для теста."
        result = ct.edit_post_sync(original, "тема", "threads")
        assert result == original  # fallback triggered because "ok" < 30 chars

    def test_returns_edited_when_long_enough(self, monkeypatch):
        """If Claude returns a long enough string, use it."""
        import bot.agents.creative_team as ct

        edited = "А" * 50  # 50 chars, well above threshold

        class _FakeClient:
            def __init__(self, *a, **kw): pass
            class messages:
                @staticmethod
                def create(*a, **kw):
                    class _R:
                        content = [type("c", (), {"text": edited})()]
                    return _R()

        monkeypatch.setattr(ct, "settings", type("s", (), {"anthropic_api_key": "x"})())
        import anthropic as _anthropic
        monkeypatch.setattr(_anthropic, "Anthropic", lambda **kw: _FakeClient())

        result = ct.edit_post_sync("original text", "тема", "instagram")
        assert result == edited
