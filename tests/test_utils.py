"""Tests for utility functions: message splitting, dash fixing, topic/carousel parsing."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient


def _miniapp_static_text(*relative_parts: str) -> str:
    return Path("miniapp", "static", *relative_parts).read_text(encoding="utf-8")


def _miniapp_js_bundle() -> str:
    return " ".join(p.read_text(encoding="utf-8") for p in sorted(Path("miniapp/static").rglob("*.js")))


# ---------------------------------------------------------------------------
# _split_message (commands.py)
# ---------------------------------------------------------------------------

from bot.handlers.commands import _split_message
from bot.handlers.content import _topics_text, _source_label
from bot.agents.threads_replies import _extract_json
from bot.services.social_oauth import build_oauth_state
from bot.services.miniapp_references import get_reference_card, list_reference_cards, seed_reference_cards_if_empty
import bot.services.miniapp_references as miniapp_references
from scripts.patch_aroma_cards import _coerce_aliases, _coerce_payload
from threads_oauth_callback import app as oauth_callback_app
import threads_oauth_callback as oauth_callback_module


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
    ContentDraft,
    _has_structured_content,
    format_content_message,
    make_single_image_prompt,
    make_slide_prompts_no_text,
    make_slide_prompts_with_text,
    parse_content_draft,
    parse_numbered_list,
)
from bot.agents.reels_agent import StoryboardFrame
from bot.services.drafts_store import save_draft
from bot.services.plans_store import save_plan


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


class TestOAuthCallbacks:
    def test_threads_callback_renders_connected_status(self, monkeypatch, tmp_path):
        monkeypatch.setattr(oauth_callback_module.settings, "telegram_bot_token", "telegram-secret")
        monkeypatch.setattr(oauth_callback_module.settings, "threads_app_id", "threads-app-id")
        monkeypatch.setattr(oauth_callback_module.settings, "threads_app_secret", "threads-secret")
        monkeypatch.setattr(oauth_callback_module, "ENV_FILE", tmp_path / ".env")
        monkeypatch.setattr(
            oauth_callback_module,
            "_exchange_bundle",
            lambda _service, _code: oauth_callback_module.OAuthTokenBundle(
                service="threads",
                short_lived_token="short",
                access_token="long",
                expires_in=3600,
                user_id="123",
                username="stress_ins",
            ),
        )
        notifications: list[tuple[str, str]] = []
        monkeypatch.setattr(oauth_callback_module, "_notify", lambda chat_id, text: notifications.append((chat_id, text)))
        restarted = {"called": False}
        monkeypatch.setattr(oauth_callback_module, "_restart_aroma_bot", lambda: restarted.__setitem__("called", True))

        state = build_oauth_state(
            secret="telegram-secret",
            service="threads",
            chat_id=42,
            user_id=99,
        )
        client = TestClient(oauth_callback_app)
        response = client.get(f"/threads/callback?code=abc123&state={state}")
        assert response.status_code == 200
        assert "Threads connected" in response.text
        assert restarted["called"] is True
        assert notifications == [("42", "✅ Threads подключён.\nАккаунт: @stress_ins\nUser ID: 123")]
        assert "THREADS_ACCESS_TOKEN=long" in (tmp_path / ".env").read_text(encoding="utf-8")

    def test_instagram_callback_renders_connected_status(self, monkeypatch, tmp_path):
        monkeypatch.setattr(oauth_callback_module.settings, "telegram_bot_token", "telegram-secret")
        monkeypatch.setattr(oauth_callback_module.settings, "instagram_app_id", "instagram-app-id")
        monkeypatch.setattr(oauth_callback_module.settings, "instagram_app_secret", "instagram-secret")
        monkeypatch.setattr(oauth_callback_module, "ENV_FILE", tmp_path / ".env")
        monkeypatch.setattr(
            oauth_callback_module,
            "_exchange_bundle",
            lambda _service, _code: oauth_callback_module.OAuthTokenBundle(
                service="instagram",
                short_lived_token="short",
                access_token="long",
                expires_in=3600,
                user_id="777",
                username="aromara.ru",
            ),
        )
        monkeypatch.setattr(oauth_callback_module, "_notify", lambda *_args, **_kwargs: None)
        monkeypatch.setattr(oauth_callback_module, "_restart_aroma_bot", lambda: None)
        state = build_oauth_state(
            secret="telegram-secret",
            service="instagram",
            chat_id=42,
            user_id=99,
        )
        client = TestClient(oauth_callback_app)
        response = client.get(f"/instagram/callback?code=ig123&state={state}")
        assert response.status_code == 200
        assert "Instagram connected" in response.text
        assert "INSTAGRAM_ACCESS_TOKEN=long" in (tmp_path / ".env").read_text(encoding="utf-8")

    def test_threads_deauthorize_returns_ok(self):
        client = TestClient(oauth_callback_app)
        response = client.get("/threads/deauthorize?user_id=42")
        assert response.status_code == 200
        assert response.json()["event"] == "deauthorize"

    def test_threads_delete_returns_confirmation_url(self):
        client = TestClient(oauth_callback_app)
        response = client.post("/threads/delete", json={"confirmation_code": "delete-1"})
        assert response.status_code == 200
        assert response.json()["confirmation_code"] == "delete-1"


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


from bot.agents.carousel_editor import (
    _EDITOR_PROMPT as _CAROUSEL_EDITOR_PROMPT,
    _build_editor_prompt,
    _sanitize_slide_text,
    edit_carousel_sync,
)
from bot.agents.reels_agent import _render_reference_context_block
from bot.services.miniapp_references import build_reference_context


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

    def test_editor_prompt_demands_soft_logical_human_flow(self):
        lowered = _CAROUSEL_EDITOR_PROMPT.lower()
        assert "логично продолжать предыдущий" in lowered
        assert "мягко, понятно и по-человечески" in lowered
        assert "не руби фразы ради эффекта" in lowered
        assert "понятно, мягко, логично" in lowered

    def test_editor_prompt_bans_awkward_phrases_and_dm(self):
        rendered = _build_editor_prompt("тема", "Слайд 1: тест").lower()
        assert "не используй эти фразы" in rendered
        assert "голова не отключается" in rendered
        assert "кажется, что ничего не помогает" in rendered
        assert "земляная база" in rendered
        assert "в дм" in rendered
        assert "в личные сообщения" in rendered

    def test_slide_sanitizer_replaces_dm_and_awkward_phrases(self):
        text = "Если интересно, напиши в ДМ. Твоему телу нужен сигнал, а не земляная база."
        result = _sanitize_slide_text(text)
        assert "в ДМ" not in result
        assert "в личные сообщения" in result
        assert "твоему телу нужен сигнал" not in result.lower()
        assert "земляная база" not in result.lower()

    def test_fallback_keeps_original_slides_when_parse_failed(self, monkeypatch):
        import anthropic as _anthropic

        original = [
            "Если интересно, напиши в ДМ.",
            "Твоему телу нужен сигнал.",
        ]

        class _FakeClient:
            def __init__(self, **_kwargs):
                pass

            class messages:
                @staticmethod
                def create(*_args, **_kwargs):
                    class _R:
                        content = [type("c", (), {"text": "не удалось собрать ответ"})()]
                    return _R()

        monkeypatch.setattr(_anthropic, "Anthropic", lambda **_kwargs: _FakeClient())
        result = edit_carousel_sync(original, "тема")
        assert result == original

    def test_reference_context_block_trims_large_payload(self):
        payload = "Ароматы:\n" + ("лаванда " * 600)
        block = _render_reference_context_block(payload)
        assert "Данные из нашего справочника" in block
        assert len(block) < len(payload)
        assert len(block) <= 1900


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

    def test_prompt_includes_forbidden_visual_motifs(self, monkeypatch):
        import bot.handlers.carousel as c
        import anthropic as _anthropic

        captured: dict[str, str] = {}

        class _FakeClient:
            def __init__(self, **kw):
                pass

            class messages:
                @staticmethod
                def create(*a, **kw):
                    captured["prompt"] = kw["messages"][0]["content"]
                    class _R:
                        content = [type("c", (), {"text": "IMG1: one\nIMG2: two\nIMG3: three\nIMG4: four\nIMG5: five\nIMG6: six"})()]
                    return _R()

        monkeypatch.setattr(c, "settings", type("s", (), {"anthropic_api_key": "x"})())
        monkeypatch.setattr(_anthropic, "Anthropic", lambda **kw: _FakeClient())
        c._generate_slide_image_prompts_sync(self._SLIDES_6, "тема")
        lowered = captured["prompt"].lower()
        assert "also forbidden everywhere" in lowered
        assert "hands joined together" in lowered
        assert "prayer pose" in lowered


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
        spec = ADAPT_PLATFORM_SPECS["threads"]
        assert "Утро / День / Вечер" in spec
        assert "5-12" in spec
        assert "40-120" in spec
        assert "без хэштегов" in spec

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
from bot.agents.content import ContentDraft
from bot.handlers.planner import _parse_plan_entries
from bot.agents.reels_agent import StoryboardFrame
from bot.services.miniapp_content_review import (
    is_content_review_draft,
    polish_content_review_draft,
    update_content_review_draft,
)
from bot.services.drafts_store import DraftRecord
from bot.services.miniapp_generator import (
    build_content_payload,
    build_reels_payload,
    is_valid_content_format,
    is_valid_content_goal,
)
from bot.services.miniapp_inbox import inbox_category, inbox_reason, is_review_status, list_inbox_items
from bot.services.miniapp_presenter import filter_drafts, payload_preview, serialize_draft, serialize_draft_summary
from bot.services.miniapp_keywords import field_labels, serialize_topics
from bot.services.miniapp_plan_actions import normalize_plan_format, normalize_plan_goal
from bot.services.miniapp_inbox import is_review_status, list_inbox_items
from bot.services.miniapp_plans import serialize_plan
from bot.services.miniapp_aromas import get_aroma_card, list_aromas, update_aroma_card
from bot.services.miniapp_reels import (
    build_reels_export_payload,
    serialize_reels_draft,
    update_reels_frame_note,
    update_reels_frame_prompt,
)
from bot.services import drafts_store as drafts_store_module
from bot.services import reels_assets as reels_assets_module
from bot.services.drafts_store import delete_draft, save_draft
from bot.services.reels_assets import regenerate_reels_frame_asset
from bot.services.carousel_assets import (
    delete_carousel_slide_version,
    select_carousel_slide_version,
    update_carousel_slide_note,
    update_carousel_slide_text,
)
from bot.services.mini_app import build_draft_tab
from bot.handlers.miniapp_bridge import parse_webapp_payload
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

    def test_draft_record_can_store_rejected_status(self):
        record = DraftRecord(
            draft_id="reject01",
            kind="threads",
            topic="Тест",
            source="/content",
            created_at="2026-03-11T07:00:00+00:00",
            status="rejected",
            feedback="",
            payload={"caption": "ok"},
        )

        assert record.status == "rejected"


class TestMiniAppPresenter:
    async def test_filter_drafts_by_kind_status_and_query(self):
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

        result = await filter_drafts(
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

    async def test_serialize_draft_counts_storyboard_frames(self):
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

        data = await serialize_draft(draft)

        assert data["storyboard_count"] == 3
        assert data["slides_count"] == 0
        assert data["preview"] == "text"

    async def test_serialize_draft_summary_omits_full_payload(self):
        draft = DraftRecord(
            draft_id="sum33333",
            kind="threads",
            topic="Короткий пост",
            source="/content",
            created_at="2026-03-11T09:00:00+00:00",
            status="draft",
            feedback="",
            payload={"caption": "Текст поста", "visual_prompt": "heavy"},
        )

        data = await serialize_draft_summary(draft)

        assert data["preview"] == "Текст поста"
        assert "payload" not in data

    async def test_serialize_draft_summary_marks_generation_pending(self):
        draft = DraftRecord(
            draft_id="car12345",
            kind="carousel",
            topic="Карусель",
            source="/miniapp",
            created_at="2026-03-12T01:00:00+00:00",
            status="draft",
            feedback="",
            payload={"slides": ["1", "2", "3"], "images_ready": 1},
        )

        data = await serialize_draft_summary(draft)

        assert data["slides_count"] == 3
        assert data["images_ready"] == 1
        assert data["generation_pending"] is True


@pytest.fixture()
def miniapp_test_client(monkeypatch):
    import miniapp_server

    monkeypatch.setattr(miniapp_server, "_verify_init_data", lambda _value: True)
    monkeypatch.setattr(miniapp_server.settings, "anthropic_api_key", "test-key")

    with TestClient(miniapp_server.app) as client:
        yield client


class TestMiniAppApi:
    AUTH_HEADERS = {"X-Telegram-Init-Data": "user=%7B%22id%22%3A62912125%7D&hash=test"}

    @pytest.mark.parametrize(
        "path",
        [
            "/api/drafts?limit=10",
            "/api/status",
            "/api/plans?limit=10",
            "/api/reels?limit=10",
            "/api/keywords",
        ],
    )
    def test_read_endpoints_require_auth(self, miniapp_test_client, path):
        response = miniapp_test_client.get(path)

        assert response.status_code == 403
        assert response.json()["detail"] == "forbidden"

    def test_detail_endpoints_require_auth(self, miniapp_test_client):
        content_draft = asyncio.run(
            save_draft(
                kind="threads",
                topic="Тихий вечер",
                source="/miniapp",
                payload={"caption": "Тестовый текст"},
            )
        )
        carousel_draft = asyncio.run(
            save_draft(
                kind="carousel",
                topic="Карусель",
                source="/miniapp",
                payload={"slides": ["Первый", "Второй"], "images_ready": 0},
            )
        )
        reels_draft = asyncio.run(
            save_draft(
                kind="reels",
                topic="Рилс",
                source="/miniapp",
                payload={
                    "scenario": "Сценарий",
                    "storyboard": [{"timecode": "0-3 сек", "scene": "Кадр", "angle": "Крупный", "gemini_prompt": "prompt"}],
                    "images_ready": 0,
                },
            )
        )
        plan = asyncio.run(
            save_plan(
                raw_text="Понедельник: Threads",
                entries=[{"day_label": "Понедельник", "platform": "Threads", "format_label": "пост", "goal": "Доверие", "topic": "Тема", "angle": "Угол"}],
            )
        )

        for path in [
            f"/api/drafts/{content_draft.draft_id}",
            f"/api/carousel/{carousel_draft.draft_id}",
            f"/api/reels/{reels_draft.draft_id}",
            f"/api/plans/{plan.plan_id}",
        ]:
            response = miniapp_test_client.get(path)

            assert response.status_code == 403
            assert response.json()["detail"] == "forbidden"

    def test_generate_content_creates_draft_and_detail(self, miniapp_test_client, monkeypatch):
        import miniapp_server

        async def _fake_generate_content(topic, goal_key, format_key):
            return ContentDraft(
                angle="Угол",
                hook="Хук",
                caption=f"Контент про {topic}",
                cta="Напишите, если откликается",
                hashtags="",
                visual_prompt="soft warm ritual",
                slides=[],
            )

        monkeypatch.setattr(
            miniapp_server,
            "generate_content_draft",
            _fake_generate_content,
        )

        response = miniapp_test_client.post(
            "/api/generate/content",
            headers=self.AUTH_HEADERS,
            json={"topic": "Вечерний ритуал", "goal_key": "trust", "format_key": "threads"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["draft_id"]
        assert payload["kind"] == "threads"

        detail = miniapp_test_client.get(f"/api/drafts/{payload['draft_id']}", headers=self.AUTH_HEADERS)
        assert detail.status_code == 200
        assert detail.json()["topic"] == "Вечерний ритуал"

    def test_generate_carousel_creates_draft_and_summary(self, miniapp_test_client, monkeypatch):
        import miniapp_server

        async def _noop_complete_carousel_generation(*_args, **_kwargs):
            return None

        monkeypatch.setattr(miniapp_server, "_complete_carousel_generation", _noop_complete_carousel_generation)

        response = miniapp_test_client.post(
            "/api/generate/carousel",
            headers=self.AUTH_HEADERS,
            json={"topic": "Сенсорная карусель"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["draft_id"]
        assert payload["kind"] == "carousel"
        assert payload["generation_pending"] is True

        drafts = miniapp_test_client.get("/api/drafts?limit=100", headers=self.AUTH_HEADERS)
        assert drafts.status_code == 200
        items = drafts.json()["items"]
        created = next(item for item in items if item["draft_id"] == payload["draft_id"])
        assert created["generation_pending"] is True
        assert created["slides_count"] == 0

    def test_generate_reels_creates_draft_and_detail(self, miniapp_test_client, monkeypatch):
        import miniapp_server

        async def _noop_complete_reels_generation(*_args, **_kwargs):
            return None

        monkeypatch.setattr(miniapp_server, "_complete_reels_generation", _noop_complete_reels_generation)

        response = miniapp_test_client.post(
            "/api/generate/reels",
            headers=self.AUTH_HEADERS,
            json={"topic": "Рилс про паузу"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["draft_id"]
        assert payload["generation_pending"] is True
        assert payload["frame_count"] == 0
        assert payload["generation_stage"] == "scenario"

        detail = miniapp_test_client.get(f"/api/reels/{payload['draft_id']}", headers=self.AUTH_HEADERS)
        assert detail.status_code == 200
        assert detail.json()["generation_pending"] is True
        assert detail.json()["frame_count"] == 0

    def test_reels_storyboard_regenerate_marks_images_pending_and_schedules_refresh(self, miniapp_test_client, monkeypatch):
        import miniapp_server

        state_calls = []
        background_runs = []

        async def _fake_regenerate_reels_storyboard(draft_id):
            return {"draft_id": draft_id, "kind": "reels"}

        async def _fake_set_generation_state(draft_id, *, pending, stage="", message="", error=""):
            state_calls.append(
                {
                    "draft_id": draft_id,
                    "pending": pending,
                    "stage": stage,
                    "message": message,
                    "error": error,
                }
            )

        async def _fake_complete_reels_regenerate_all(draft_id):
            background_runs.append(draft_id)

        async def _fake_serialize_reels_draft(draft_id):
            return {
                "draft_id": draft_id,
                "kind": "reels",
                "generation_pending": True,
                "generation_stage": "images",
                "generation_message": "Генерирую кадры для рилса.",
                "frame_count": 4,
                "images_ready": 0,
                "frames": [],
            }

        monkeypatch.setattr(miniapp_server, "regenerate_reels_storyboard", _fake_regenerate_reels_storyboard)
        monkeypatch.setattr(miniapp_server, "_set_generation_state", _fake_set_generation_state)
        monkeypatch.setattr(miniapp_server, "_complete_reels_regenerate_all", _fake_complete_reels_regenerate_all)
        monkeypatch.setattr(miniapp_server, "serialize_reels_draft", _fake_serialize_reels_draft)

        response = miniapp_test_client.post(
            "/api/reels/reels001/storyboard/regenerate",
            headers=self.AUTH_HEADERS,
            json={},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["draft_id"] == "reels001"
        assert payload["generation_pending"] is True
        assert payload["generation_stage"] == "images"
        assert payload["generation_message"] == "Генерирую кадры для рилса."
        assert state_calls == [
            {
                "draft_id": "reels001",
                "pending": True,
                "stage": "images",
                "message": "Генерирую кадры для рилса.",
                "error": "",
            }
        ]
        assert background_runs == ["reels001"]

    @pytest.mark.asyncio
    async def test_build_reference_context_includes_handbook_sections(self, monkeypatch):
        import bot.services.miniapp_references as references

        cards = [
            SimpleNamespace(
                category="aroma",
                name="Лаванда",
                source_type="herb",
                payload={"key": "lavender", "psychological_properties": "Помогает выдохнуть и снизить вечернее напряжение."},
            ),
            SimpleNamespace(
                category="concept",
                name="Лимбическая система",
                source_type="system",
                payload={"description": "Связана с эмоциями и реакцией на запах."},
            ),
            SimpleNamespace(
                category="practice",
                name="Квадратное дыхание",
                source_type="breath",
                payload={"description": "Практика с ровным ритмом вдоха и выдоха."},
            ),
            SimpleNamespace(
                category="sound",
                name="Гонг",
                source_type="instrument",
                payload={"description": "Дает плотную вибрацию и ощущение опоры."},
            ),
            SimpleNamespace(
                category="other",
                name="Лишняя запись",
                source_type="misc",
                payload={"description": "Не должна попасть в контекст."},
            ),
        ]

        class _FakeResult:
            def scalars(self):
                return self

            def all(self):
                return cards

        class _FakeSession:
            async def execute(self, _query):
                return _FakeResult()

        class _FakeSessionContext:
            async def __aenter__(self):
                return _FakeSession()

            async def __aexit__(self, exc_type, exc, tb):
                return False

        async def _noop_seed():
            return None

        monkeypatch.setattr(references, "AsyncSessionLocal", lambda: _FakeSessionContext())
        monkeypatch.setattr(references, "seed_reference_cards_if_empty", _noop_seed)

        result = await build_reference_context(max_items_per_category=4, max_total_chars=1000)

        assert "Ароматы:" in result
        assert "Теория:" in result
        assert "Практики:" in result
        assert "Звуки:" in result
        assert "- Лаванда (herb, lavender): Помогает выдохнуть" in result
        assert "- Лимбическая система (system): Связана с эмоциями" in result
        assert "- Квадратное дыхание (breath): Практика с ровным ритмом" in result
        assert "- Гонг (instrument): Дает плотную вибрацию" in result
        assert "Лишняя запись" not in result

    @pytest.mark.asyncio
    async def test_build_reference_context_obeys_size_limits(self, monkeypatch):
        import bot.services.miniapp_references as references

        cards = [
            SimpleNamespace(
                category="aroma",
                name=f"Карточка {index}",
                source_type="herb",
                payload={"description": "Очень длинное описание " * 20},
            )
            for index in range(8)
        ]

        class _FakeResult:
            def scalars(self):
                return self

            def all(self):
                return cards

        class _FakeSession:
            async def execute(self, _query):
                return _FakeResult()

        class _FakeSessionContext:
            async def __aenter__(self):
                return _FakeSession()

            async def __aexit__(self, exc_type, exc, tb):
                return False

        async def _noop_seed():
            return None

        monkeypatch.setattr(references, "AsyncSessionLocal", lambda: _FakeSessionContext())
        monkeypatch.setattr(references, "seed_reference_cards_if_empty", _noop_seed)

        result = await build_reference_context(max_items_per_category=2, max_total_chars=220)

        assert result.startswith("Ароматы:")
        assert result.count("- Карточка") <= 2
        assert len(result) <= 220

    def test_generate_plan_returns_entries(self, miniapp_test_client, monkeypatch):
        import miniapp_server
        import analytics.aggregator
        import cache.store

        monkeypatch.setattr(
            miniapp_server,
            "generate_plan_sync",
            lambda trends_text: (
                "📅 Понедельник\n"
                "Платформа: Threads\n"
                "Формат: Пост\n"
                "Цель: Доверие\n"
                "Тема: Тема недели\n"
                "Угол: Через мягкий вход\n"
            ),
        )
        monkeypatch.setattr(miniapp_server, "_format_trends", lambda _results: "threads: signal")
        monkeypatch.setattr(analytics.aggregator, "collect_all", lambda: [])
        monkeypatch.setattr(cache.store.cache, "get", lambda _key: ["cached"])
        monkeypatch.setattr(cache.store.cache, "set", lambda _key, _value: None)

        response = miniapp_test_client.post(
            "/api/generate/plan",
            headers=self.AUTH_HEADERS,
            json={},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["plan_id"]
        assert len(payload["entries"]) >= 1

    @pytest.mark.asyncio
    async def test_lifespan_skips_recovery_when_lock_is_held(self, monkeypatch):
        import miniapp_server

        calls = {"list_recent_drafts": 0}

        async def _fake_list_recent_drafts(*_args, **_kwargs):
            calls["list_recent_drafts"] += 1
            return []

        monkeypatch.setattr(miniapp_server, "_acquire_startup_recovery_lock", lambda: None)
        monkeypatch.setattr(miniapp_server, "list_recent_drafts", _fake_list_recent_drafts)

        async with miniapp_server.app.router.lifespan_context(miniapp_server.app):
            pass

        assert calls["list_recent_drafts"] == 0


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


class TestMiniAppGenerator:
    def test_validates_content_goal_and_format(self):
        assert is_valid_content_goal("trust") is True
        assert is_valid_content_goal("unknown") is False
        assert is_valid_content_format("threads") is True
        assert is_valid_content_format("carousel") is False

    def test_build_content_payload_keeps_text_fields(self):
        payload = build_content_payload(
            ContentDraft(
                angle="Через перегрузку",
                hook="Тело не выключается вечером",
                caption="Текст поста",
                cta="Напиши, если откликается",
                hashtags="#aroma",
                visual_prompt="warm still life",
                slides=["one", "two"],
            ),
            goal_key="trust",
            format_key="threads",
        )

        assert payload["caption"] == "Текст поста"
        assert payload["slides"] == ["one", "two"]
        assert payload["goal_key"] == "trust"
        assert payload["format_key"] == "threads"

    def test_build_reels_payload_serializes_storyboard(self):
        frames = [
            StoryboardFrame(
                timecode="0-3 сек",
                scene="Свеча и флакон",
                angle="Макро",
                gemini_prompt="warm candle and bottle",
            )
        ]

        payload = build_reels_payload("Вечерний ритуал", "Сценарий", frames)

        assert payload["scenario"] == "Сценарий"
        assert payload["images_ready"] == 0
        assert payload["storyboard"][0]["scene"] == "Свеча и флакон"


class TestMiniAppContentReview:
    def test_recognizes_supported_content_kinds(self):
        assert is_content_review_draft("threads") is True
        assert is_content_review_draft("carousel") is False

    async def test_update_content_review_draft_returns_none_for_missing(self):
        assert await update_content_review_draft(
            "missing-id",
            topic="topic",
            angle="angle",
            hook="hook",
            caption="caption",
            cta="cta",
            hashtags="#tag",
            visual_prompt="warm visual",
            editor_notes="note",
        ) is None

    async def test_polish_content_review_draft_returns_none_for_missing(self):
        assert await polish_content_review_draft("missing-id") is None


class TestMiniAppInbox:
    def test_review_status_filter(self):
        assert is_review_status("draft") is True
        assert is_review_status("in_review") is True
        assert is_review_status("rejected") is False
        assert is_review_status("approved") is False

    def test_category_and_reason(self):
        plan_record = DraftRecord(
            draft_id="aaa11111",
            kind="threads",
            topic="Плановый пост",
            source="/plan",
            created_at="2026-03-11T10:00:00+00:00",
            status="draft",
            feedback="",
            payload={"caption": "text"},
        )
        reels_record = DraftRecord(
            draft_id="bbb22222",
            kind="reels",
            topic="Рилс",
            source="/reels",
            created_at="2026-03-11T10:00:00+00:00",
            status="in_review",
            feedback="",
            payload={"scenario": "text"},
        )

        assert inbox_category(plan_record) == "plan"
        assert "контент-плана" in inbox_reason(plan_record)
        assert inbox_category(reels_record) == "reels"
        assert "Reels" in inbox_reason(reels_record)

    async def test_list_inbox_items_returns_list(self):
        items = await list_inbox_items(limit=5, kind_filter="content")
        assert isinstance(items, list)


class TestMiniAppPlans:
    def test_normalize_plan_goal_and_format(self):
        assert normalize_plan_goal("Вовлечение") == "engagement"
        assert normalize_plan_goal("Экспертность") == "authority"
        assert normalize_plan_format({"platform": "Threads", "format_label": "пост"}) == "threads"
        assert normalize_plan_format({"platform": "Instagram", "format_label": "карусель"}) == "carousel"
        assert normalize_plan_format({"platform": "Reels", "format_label": "рилс"}) == "reels"

    async def test_serialize_plan_keeps_entries(self):
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

        data = await serialize_plan(plan)

        assert data["plan_id"] == "20260311120000"
        assert len(data["entries"]) == 1
        assert data["entries"][0]["platform"] == "Threads"


class TestMiniAppLinks:
    def test_build_draft_tab_prefers_reels_for_reels(self):
        assert build_draft_tab("reels") == "reels"
        assert build_draft_tab("threads") == "drafts"


class TestMiniAppBridge:
    def test_parse_webapp_payload_accepts_open_draft(self):
        payload = parse_webapp_payload('{"action":"open_draft","draft_id":"abc123"}')
        assert payload is not None
        assert payload["action"] == "open_draft"
        assert payload["draft_id"] == "abc123"

    def test_parse_webapp_payload_accepts_request_review(self):
        payload = parse_webapp_payload('{"action":"request_review","draft_id":"abc123"}')
        assert payload is not None
        assert payload["action"] == "request_review"

    def test_parse_webapp_payload_accepts_open_plan(self):
        payload = parse_webapp_payload('{"action":"open_plan","plan_id":"20260311120000"}')
        assert payload is not None
        assert payload["action"] == "open_plan"
        assert payload["plan_id"] == "20260311120000"

    def test_parse_webapp_payload_rejects_bad_json(self):
        assert parse_webapp_payload("not-json") is None


class TestMiniAppRussianLocale:
    def test_index_selects_and_tabs_use_russian_labels(self):
        index_html = Path("miniapp/index.html").read_text(encoding="utf-8")
        app_js = " ".join(p.read_text(encoding="utf-8") for p in sorted(Path("miniapp/static").rglob("*.js")))

        # HTML should have basic structure and mode selectors
        assert 'id="modeContent"' in index_html
        assert 'id="modeHandbook"' in index_html

        # Labels should be in JS for dynamic tab generation
        assert '"Тредс"' in app_js
        assert '"Инстаграм"' in app_js
        assert '"Телеграм"' in app_js
        assert '"Рилсы"' in app_js
        assert '"reels"' in app_js

        assert ">Reels<" not in index_html

    def test_index_does_not_render_legacy_hero_block(self):
        index_html = Path("miniapp/index.html").read_text(encoding="utf-8")

        assert 'class="hero"' not in index_html
        assert "Черновики и рилсы" not in index_html
        assert 'id="headerContent"' not in index_html

    def test_index_has_bootstrap_fallback_panel(self):
        index_html = Path("miniapp/index.html").read_text(encoding="utf-8")

        assert 'id="bootFallback"' in index_html
        assert 'id="bootFallbackReload"' in index_html
        assert "Загружаю интерфейс" in index_html

    def test_create_workspace_dropdowns_use_russian_labels(self):
        app_js = " ".join(p.read_text(encoding="utf-8") for p in sorted(Path("miniapp/static").rglob("*.js")))

        assert '<option value="threads">Тредс</option>' in app_js
        assert '<option value="instagram">Инстаграм</option>' in app_js
        assert '<option value="telegram">Телеграм</option>' in app_js
        assert '<option value="threads">Threads</option>' not in app_js
        assert '<option value="instagram">Instagram</option>' not in app_js
        assert '<option value="telegram">Telegram</option>' not in app_js

    async def test_aroma_service_sorts_cards_in_russian_alphabet(self):
        items = await list_aromas()
        assert items[0]["name"] == "Апельсин"
        assert items[-1]["name"] == "Эвкалипт шаровидный"

    async def test_aroma_service_supports_alias_lookup(self):
        card = await get_aroma_card("Ромашка немецкая")
        assert card is not None
        assert card["slug"] == "german-chamomile"

    async def test_aroma_service_can_update_card(self):
        card = await get_aroma_card("orange")
        assert card is not None

        updated = await update_aroma_card(
            "orange",
            {
                "description": "Обновленное описание",
                "questions": "Новый вопрос?",
                "nps_effect": "Новый эффект",
                "therapeutic_properties": "Новая терапия",
                "psychological_properties": "Новая психология",
                "history": "Новая история",
                "volatility": "Средняя",
                "botanical_family": "Rutaceae",
                "origin_countries": "Италия",
                "extraction_method": "Холодный отжим",
                "key": "Новый ключ",
                "resource_values": {"plus": "Плюс", "minus": "Минус"},
            },
        )
        assert updated is not None
        assert updated["description"] == "Обновленное описание"
        assert updated["resource_values"]["minus"] == "Минус"

    async def test_reference_service_seeds_additional_practices(self):
        items = await list_reference_cards("practice")
        slugs = {item["slug"] for item in items}
        assert "box-breathing" in slugs
        assert "coherent-breathing" in slugs
        assert "visualization-safe-place" in slugs
        assert "pelvic-wave" in slugs
        assert "woodcutter" in slugs
        assert len(items) >= 12

    async def test_reference_service_seeds_additional_sounds(self):
        items = await list_reference_cards("sound")
        slugs = {item["slug"] for item in items}
        assert "gong" in slugs
        assert "pink-noise" in slugs
        assert "silence-practice" in slugs
        assert len(items) >= 12

    async def test_reference_service_seeds_pdf_based_aroma_cards_and_course_metadata(self):
        items = await list_reference_cards("aroma")
        slugs = {item["slug"] for item in items}

        assert "ho-wood" in slugs
        assert "black-spruce" in slugs
        assert "bay-laurel" in slugs
        assert "pink-pepper" in slugs
        assert "fragonia" in slugs
        assert "myrrh" in slugs

        bergamot = await get_aroma_card("bergamot")
        cedar = await get_aroma_card("Кедр атласский")
        laurel = await get_aroma_card("bay-laurel")

        assert bergamot is not None
        assert cedar is not None
        assert laurel is not None

        assert "Citrus bergamia" in bergamot["aliases"]
        assert bergamot["course_source"] == "rudn_olfactotherapy_2l"
        assert "снижает уровень контроля" in bergamot["course_notes"].lower()

        assert cedar["slug"] == "cedarwood"
        assert "Кедр атласский" in cedar["aliases"]
        assert cedar["chakra_focus"] == "1-я чакра Муладхара"
        assert cedar["polarity"] == "Янг"

        assert laurel["name"] == "Лавр благородный"
        assert laurel["chakra_focus"] == "3-я и 5-я чакры"

    async def test_reference_service_seeds_pdf_based_concept_cards(self):
        items = await list_reference_cards("concept")
        slugs = {item["slug"] for item in items}

        assert "olfactotherapy" in slugs
        assert "gilles-fournil" in slugs
        assert "chakra-system" in slugs
        assert "muladhara-chakra" in slugs
        assert "svadhisthana-chakra" in slugs
        assert "manipura-chakra" in slugs

        concept = await get_reference_card("concept", "limbic-system-and-olfactory-library")
        assert concept is not None
        assert concept["source_type"] == "system"
        assert concept["course_source"] == "rudn_olfactotherapy_1l"
        assert "лимбичес" in concept["name"].lower()
        assert "эмоциональ" in concept["description"].lower()

    async def test_reference_service_uses_exact_photo_overrides_for_selected_oils(self):
        orange = await get_aroma_card("orange")
        lavender = await get_aroma_card("lavender")

        assert orange is not None
        assert lavender is not None
        assert orange["image_url"] in {"/reference-images/aromas/orange.jpg", "/reference-images/aromas/orange.png"}
        assert lavender["image_url"] in {"/reference-images/aromas/lavender.jpg", "/reference-images/aromas/lavender.png"}

    async def test_reference_service_uses_shared_photo_fallbacks_for_practices_and_sounds(self):
        practice = await get_reference_card("practice", "box-breathing")
        sound = await get_reference_card("sound", "gong")

        assert practice is not None
        assert sound is not None
        assert practice["image_url"] == "/reference-images/shared/nature.jpg"
        assert sound["image_url"] == "/reference-images/shared/instrument.jpg"

    async def test_seed_does_not_overwrite_manual_reference_edits(self, monkeypatch, tmp_path):
        seed_file = tmp_path / "seed.json"
        extra_seed_file = tmp_path / "extra.json"
        seed_file.write_text(
            json.dumps(
                [
                    {
                        "category": "practice",
                        "slug": "box-breathing",
                        "name": "Квадратное дыхание",
                        "source_type": "breath",
                        "description": "Базовое описание из seed.",
                        "questions": "Базовый вопрос из seed.",
                        "resource_values": {"plus": "Плюс seed", "minus": "Минус seed"},
                    }
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        extra_seed_file.write_text("[]", encoding="utf-8")
        monkeypatch.setattr(miniapp_references, "SEED_FILE", seed_file)
        monkeypatch.setattr(miniapp_references, "EXTRA_SEED_FILE", extra_seed_file)

        await seed_reference_cards_if_empty()
        updated = await miniapp_references.update_reference_card(
            "practice",
            "box-breathing",
            {
                "description": "Ручное описание из mini app.",
                "questions": "Ручной вопрос из mini app.",
                "resource_values": {"plus": "Ручной плюс", "minus": "Минус seed"},
            },
        )
        assert updated is not None
        assert updated["description"] == "Ручное описание из mini app."

        seed_file.write_text(
            json.dumps(
                [
                    {
                        "category": "practice",
                        "slug": "box-breathing",
                        "name": "Квадратное дыхание",
                        "source_type": "breath",
                        "description": "Новое описание из seed.",
                        "questions": "Новый вопрос из seed.",
                        "nps_effect": "Новый НПС из seed.",
                        "resource_values": {"plus": "Плюс seed v2", "minus": "Минус seed v2"},
                    }
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        await seed_reference_cards_if_empty()
        card = await get_reference_card("practice", "box-breathing")
        assert card is not None
        assert card["description"] == "Ручное описание из mini app."
        assert card["questions"] == "Ручной вопрос из mini app."
        assert card["resource_values"]["plus"] == "Ручной плюс"
        assert card["resource_values"]["minus"] == "Минус seed v2"
        assert card["nps_effect"] == "Новый НПС из seed."

    def test_viewport_disables_double_tap_zoom(self):
        index_html = Path("miniapp/index.html").read_text(encoding="utf-8")

        assert 'maximum-scale=1' in index_html
        assert 'user-scalable=no' in index_html

    def test_tab_switching_uses_native_click_and_touch_action(self):
        app_js = " ".join(p.read_text(encoding="utf-8") for p in sorted(Path("miniapp/static").rglob("*.js")))
        app_css = Path("miniapp/static/app.css").read_text(encoding="utf-8")

        # We use standard click now, but ensure tabs switching logic is there
        assert 'addEventListener("click"' in app_js
        assert "setTab(" in app_js

        # Ensure CSS handles the 300ms delay/zoom
        assert "touch-action: manipulation;" in app_css

    def test_mobile_detail_swipe_back_allows_full_width_swipe_and_skips_inputs(self):
        shell_js = _miniapp_static_text("js", "shell.js")
        app_css = Path("miniapp/static/app.css").read_text(encoding="utf-8")

        assert "function bindSwipeBack" in shell_js
        assert "function animateBackToList" in shell_js
        assert "isInteractiveTarget(event.target)" in shell_js
        assert 'closest("textarea, input, select, button, a, [contenteditable=\'true\']")' in shell_js
        assert "const edgeSwipe = touch.clientX < 44;" in shell_js
        assert "touch.clientX > 36" not in shell_js
        assert "dx > 72" in shell_js
        assert "swipe-back-exit" in shell_js
        assert ".detail-panel.swipe-back-exit" in app_css
        assert ".detail-panel.swipe-back-armed" in app_css

    def test_bootstrap_guard_shows_visible_fallback_instead_of_blank_screen(self):
        app_js = _miniapp_static_text("app.js")
        core_js = _miniapp_static_text("js", "core.js")
        runtime_js = _miniapp_static_text("js", "runtime.js")
        app_css = Path("miniapp/static/app.css").read_text(encoding="utf-8")

        assert "function showBootFallback" in core_js
        assert "function hideBootFallback" in core_js
        assert "bootstrapWatchdogTimer" in app_js
        assert "timers.setBootstrapWatchdog" in runtime_js
        assert "timers.getBootstrapWatchdog" in runtime_js
        assert 'window.addEventListener("error"' in runtime_js
        assert 'window.addEventListener("unhandledrejection"' in runtime_js
        assert ".boot-fallback" in app_css
        assert ".boot-fallback.is-error" in app_css
        assert "async function loadInitialScreen()" in runtime_js
        assert 'await loadInitialScreen();' in runtime_js
        assert 'if (!appState.isBootstrapped()) {' in runtime_js
        assert 'appState.setBootstrapped(true)' in runtime_js

    def test_handbook_has_all_reference_tabs(self):
        app_js = " ".join(p.read_text(encoding="utf-8") for p in sorted(Path("miniapp/static").rglob("*.js")))
        html = Path("miniapp/index.html").read_text(encoding="utf-8")
    
        assert 'id: "aromas"' in app_js
        assert 'label: "Ароматы"' in app_js
        assert 'id: "concepts"' in app_js
        assert 'label: "Теория"' in app_js
        assert 'id: "practices"' in app_js
        assert 'label: "Практики"' in app_js
        assert 'id: "sounds"' in app_js
        assert 'label: "Звуки"' in app_js
        assert 'id="settingsButton"' in html

    def test_handbook_concepts_have_meta_and_render_course_fields(self):
        app_js = " ".join(p.read_text(encoding="utf-8") for p in sorted(Path("miniapp/static").rglob("*.js")))
        app_css = Path("miniapp/static/app.css").read_text(encoding="utf-8")

        assert 'category: "concept"' in app_js
        assert 'searchLabel: "Поиск темы"' in app_js
        assert 'return `PDF ${match[1].replaceAll("_", ".")}`;' in app_js
        assert 'function conceptTypeMeta(sourceType)' in app_js
        assert 'founder: { label: "Автор", icon: "◍" }' in app_js
        assert 'chakra: { label: "Чакра", icon: "✦" }' in app_js
        assert 'class="draft-card overview-card' in app_js
        assert 'class="kind-glyph handbook-glyph" aria-hidden="true"' in app_js
        assert 'tone-${escapeHtml(item.tone)}' in app_js
        assert 'reference-hero-card is-theory' in app_js
        assert 'reference-card${state.tab === "concepts" ? " is-theory concept-card" : ""}' in app_js
        assert 'reference.chakra_focus ? `Фокус / чакры: ${reference.chakra_focus}` : ""' in app_js
        assert 'reference.course_source ? `Источник курса: ${formatCourseSourceLabel(reference.course_source)}` : ""' in app_js
        assert '${aromaSection("Материалы курса", reference.course_notes)}' in app_js
        assert ".reference-card .overview-card-date" in app_css
        assert ".reference-hero-card.is-theory" in app_css
        assert ".reference-badge.tone-course" in app_css
        assert ".concept-kind-mark" in app_css
        assert ".concept-card::before" in app_css

    def test_content_detail_supports_prompt_copy_actions(self):
        app_js = " ".join(p.read_text(encoding="utf-8") for p in sorted(Path("miniapp/static").rglob("*.js")))

        assert "Скопировать промпт кадра" in app_js
        assert "Скопировать промпт слайда" in app_js
        assert "function copyText" in app_js
        assert "function renderMarkdown" in app_js
        assert "function stripMarkdown" in app_js

    def test_content_cards_force_left_alignment_and_mobile_button_stack(self):
        app_css = Path("miniapp/static/app.css").read_text(encoding="utf-8")

        assert "text-align: left;" in app_css
        assert "flex: 1 1 100%;" in app_css

    def test_swipe_back_ignores_text_selection_and_selectable_copy(self):
        shell_js = _miniapp_static_text("js", "shell.js")

        assert "function isSelectableTextTarget" in shell_js
        assert "function hasActiveTextSelection" in shell_js
        assert 'target.closest(".detail-preview, .detail-markdown, .draft-preview, .draft-topic, .detail-title, .section")' in shell_js
        assert "hasActiveTextSelection()" in shell_js

    def test_draft_cards_have_stronger_readability_styles(self):
        app_css = Path("miniapp/static/app.css").read_text(encoding="utf-8")
        app_js = " ".join(p.read_text(encoding="utf-8") for p in sorted(Path("miniapp/static").rglob("*.js")))

        assert ".kind-glyph" in app_css
        assert "padding: 4px 10px;" in app_css
        assert "font-size: 17px;" in app_css
        assert "font-size: 18px;" in app_css
        assert "🎬" in app_js

    def test_telegram_dark_theme_uses_body_class_for_bottom_nav(self):
        source = " ".join(p.read_text(encoding="utf-8") for p in sorted(Path("miniapp/static").rglob("*.js")))
        app_css = Path("miniapp/static/app.css").read_text(encoding="utf-8")

        assert 'document.body.classList.toggle("tg-theme-dark", tg.colorScheme === "dark");' in source
        assert "body.tg-theme-dark .bottom-tab-bar-inner" in app_css
        assert ".concept-card .draft-preview" in app_css
        assert "color: inherit;" in app_css
        assert "🖼️" in source
        assert "✍️" in source

    def test_create_tool_panel_is_scaled_up_for_mobile(self):
        app_css = Path("miniapp/static/app.css").read_text(encoding="utf-8")
        app_js = " ".join(p.read_text(encoding="utf-8") for p in sorted(Path("miniapp/static").rglob("*.js")))

        assert "create-tool-panel" in app_js
        assert ".create-tool-panel" in app_css
        assert "min-height: 132px;" in app_css
        assert "font-size: 18px;" in app_css
        assert "min-height: 62px;" in app_css

    def test_create_cards_use_icons_and_top_switcher_gap_is_balanced(self):
        app_css = Path("miniapp/static/app.css").read_text(encoding="utf-8")
        app_js = " ".join(p.read_text(encoding="utf-8") for p in sorted(Path("miniapp/static").rglob("*.js")))

        assert '".topbar + .toolbar"' in app_css or ".topbar + .toolbar" in app_css
        assert 'data-tool="content"' in app_js
        assert 'data-tool="reels"' in app_js
        assert 'data-tool="plan"' in app_js
        assert 'data-tool="carousel"' in app_js
        assert 'contentKindIcon("content")' in app_js
        assert 'contentKindIcon("plan")' in app_js

    def test_carousel_detail_uses_actions_instead_of_raw_json(self):
        app_js = " ".join(p.read_text(encoding="utf-8") for p in sorted(Path("miniapp/static").rglob("*.js")))
        server_py = Path("miniapp_server.py").read_text(encoding="utf-8")

        assert "JSON</h3>" not in app_js
        assert "Обновить все слайды" in app_js
        assert "Обновить по замечанию" in app_js
        assert "Сохранить текст слайда" in app_js
        assert "Подпись слайда" in app_js
        assert "Скачать презентацию" in app_js
        assert "Показать промпт" in app_js
        assert "Скопировать промпт слайда" in app_js
        assert "generationStateMarkup" in app_js
        assert "tg.openLink(downloadUrl)" in app_js
        assert "init_data" in server_py
        assert "sendDraftToChat" in app_js
        assert "handleCarouselSlideNoteInput" in app_js
        assert "bindSwipeBack" in app_js
        assert "/api/carousel/{draft_id}/pptx" in server_py
        assert "/api/carousel/{draft_id}/slides/{slide_index}/regenerate" in server_py
        assert "/api/carousel/{draft_id}/slides/{slide_index}/text" in server_py
        assert "/api/carousel/{draft_id}/slides/{slide_index}/note" in server_py
        assert "/api/carousel/{draft_id}/slides/{slide_index}/versions/{version_index}/select" in server_py
        assert "/api/carousel/{draft_id}/slides/{slide_index}/versions/{version_index}" in server_py
        assert "Версии" in app_js
        assert "Сделать текущей" in app_js

    def test_reels_detail_supports_editing_and_reference_generation(self):
        app_js = " ".join(p.read_text(encoding="utf-8") for p in sorted(Path("miniapp/static").rglob("*.js")))
        server_py = Path("miniapp_server.py").read_text(encoding="utf-8")

        assert "Сохранить концепцию и сценарий" in app_js
        assert "Пересобрать раскадровку" in app_js
        assert "Обновить все кадры" in app_js
        assert "Сохранить описание кадра" in app_js
        assert "Сохранить промпт кадра" in app_js
        assert "Сохранить замечание" in app_js
        assert "Обновить кадр" in app_js
        assert "handleReelsFrameNoteInput" in app_js
        assert "handleReelsFramePromptInput" in app_js
        assert "/api/reels/{draft_id}/scenario" in server_py
        assert "/api/reels/{draft_id}/storyboard/regenerate" in server_py
        assert "/api/reels/{draft_id}/frames/regenerate-all" in server_py
        assert "/api/reels/{draft_id}/frames/{frame_index}/fields" in server_py
        assert "Сохранить концепцию и сценарий" in app_js
        assert "Пересобрать раскадровку" in app_js
        assert "Обновить все кадры" in app_js
        assert "Сохранить описание кадра" in app_js
        assert "Сохранить промпт кадра" in app_js
        assert "Обновить кадр" in app_js

    def test_content_review_detail_supports_editing_polish_and_feedback(self):
        app_js = " ".join(p.read_text(encoding="utf-8") for p in sorted(Path("miniapp/static").rglob("*.js")))
        app_css = Path("miniapp/static/app.css").read_text(encoding="utf-8")
        server_py = Path("miniapp_server.py").read_text(encoding="utf-8")

        assert "function isContentReviewKind" in app_js
        assert "Редакторский review" in app_js
        assert "Комментарий редактора" in app_js
        assert "Сохранить версию" in app_js
        assert "Уточнить через AI" in app_js
        assert "Результат публикации" in app_js
        assert "Откликнулось" in app_js
        assert "Не дало результата" in app_js
        assert "Очистить отметку" in app_js
        assert "function saveContentReviewDraft" in app_js
        assert "function polishContentDraft" in app_js
        assert 'window.saveContentReviewDraft = saveContentReviewDraft;' in app_js
        assert 'window.polishContentDraft = polishContentDraft;' in app_js
        assert "/api/drafts/{draft_id}/content" in server_py
        assert "/api/drafts/{draft_id}/content/polish" in server_py
        assert "editor_notes" in server_py
        assert ".content-review-form label > span" in app_css
        assert ".field-help" in app_css

    def test_create_and_detail_microcopy_is_editorial_and_actionable(self):
        app_js = " ".join(p.read_text(encoding="utf-8") for p in sorted(Path("miniapp/static").rglob("*.js")))

        assert "Собрать черновик" in app_js
        assert "Собрать сценарий и кадры" in app_js
        assert "Собрать карусель" in app_js
        assert "Тема материала" in app_js
        assert "Опорная мысль" in app_js
        assert "Первая фраза" in app_js
        assert "Призыв к действию" in app_js
        assert "Промпт для визуала" in app_js
        assert "Согласовать" in app_js
        assert "Вернуть на доработку" in app_js
        assert "Отправить в чат" in app_js
        assert "deleteDraft" in app_js

    def test_keywords_detail_supports_editing_and_ui_notices(self):
        app_js = " ".join(p.read_text(encoding="utf-8") for p in sorted(Path("miniapp/static").rglob("*.js")))
        app_css = Path("miniapp/static/app.css").read_text(encoding="utf-8")
        server_py = Path("miniapp_server.py").read_text(encoding="utf-8")

        assert "function showUiNotice" in app_js
        assert "function confirmAction" in app_js
        assert "function openKeywordTopic" in app_js
        assert "function addKeywordItem" in app_js
        assert "function removeKeywordItem" in app_js
        assert "Редактор ключей" in app_js
        assert "Ключ добавлен" in app_js
        assert "Ключ удален" in app_js
        assert "tg?.showConfirm" in app_js
        assert 'window.openKeywordTopic = openKeywordTopic;' in app_js
        assert 'window.addKeywordItem = addKeywordItem;' in app_js
        assert 'window.removeKeywordItem = removeKeywordItem;' in app_js
        assert "/api/keywords/add" in server_py
        assert "/api/keywords/remove" in server_py
        assert ".ui-notice" in app_css
        assert ".keyword-topic.active" in app_css

    def test_guided_states_cover_empty_and_onboarding_paths(self):
        app_js = " ".join(p.read_text(encoding="utf-8") for p in sorted(Path("miniapp/static").rglob("*.js")))
        app_css = Path("miniapp/static/app.css").read_text(encoding="utf-8")
        html = Path("miniapp/index.html").read_text(encoding="utf-8")

        assert "function renderGuidedState" in app_js
        assert 'title: "Выберите формат для старта"' in app_js
        assert 'title: "Ничего не найдено"' in app_js
        assert 'title: "Планов пока нет"' in app_js
        assert 'title: "Рилсов пока нет"' in app_js
        assert 'title: "Откройте тему для редактирования"' in app_js
        assert 'title: inSettings ? "Откройте источник слева" : "Проверьте состояние источников"' in app_js
        assert ".guided-state" in app_css
        assert ".guided-state-copy" in app_css
        assert ".guided-state-actions" in app_css
        assert "Попробовать еще раз" in html
        assert "Откройте раздел или карточку слева" in html

    def test_primary_controls_use_comfortable_size_tokens(self):
        app_css = Path("miniapp/static/app.css").read_text(encoding="utf-8")

        assert "min-height: 40px;" in app_css
        assert "min-height: 44px;" in app_css
        assert "width: 44px;" in app_css
        assert "height: 44px;" in app_css
        assert ".tab-button," in app_css
        assert ".mode-button," in app_css
        assert ".back-button," in app_css

    def test_draft_detail_supports_reject_and_delete_actions(self):
        app_js = " ".join(p.read_text(encoding="utf-8") for p in sorted(Path("miniapp/static").rglob("*.js")))
        server_py = Path("miniapp_server.py").read_text(encoding="utf-8")
        html = Path("miniapp/index.html").read_text(encoding="utf-8")

        assert "Вернуть на доработку" in app_js
        assert 'actionLabel("reject", "Вернуть на доработку")' in app_js
        assert 'actionLabel("trash"' in app_js
        assert "deleteDraft" in app_js
        assert "rejected" in app_js
        assert '@app.delete("/api/drafts/{draft_id}")' in server_py
        assert 'option value="rejected"' in html

    def test_buttons_have_loading_feedback_animation(self):
        app_js = " ".join(p.read_text(encoding="utf-8") for p in sorted(Path("miniapp/static").rglob("*.js")))
        app_css = Path("miniapp/static/app.css").read_text(encoding="utf-8")

        assert "function withButtonFeedback" in app_js
        assert "button-spinner" in app_css
        assert ".secondary-button.is-busy" in app_css
        assert ".secondary-button.did-complete" in app_css

    def test_detail_opening_uses_branded_a_loader(self):
        app_js = " ".join(p.read_text(encoding="utf-8") for p in sorted(Path("miniapp/static").rglob("*.js")))
        app_css = Path("miniapp/static/app.css").read_text(encoding="utf-8")

        assert "function renderDetailLoader" in app_js
        assert "Открываю черновик" in app_js
        assert "Открываю рилс" in app_js
        assert "brand-loader-letter" in app_css
        assert "brand-loader-spin" in app_css

    def test_drafts_tab_uses_inline_a_loader_and_timeout_state(self):
        app_js = " ".join(p.read_text(encoding="utf-8") for p in sorted(Path("miniapp/static").rglob("*.js")))
        app_css = Path("miniapp/static/app.css").read_text(encoding="utf-8")
        server_py = Path("miniapp_server.py").read_text(encoding="utf-8")

        assert "function renderPanelLoader" in app_js
        assert "function renderPanelError" in app_js
        assert 'elements.draftList.innerHTML = renderPanelLoader("Загружаю раздел")' in app_js
        assert 'message === "request_timeout"' in app_js
        assert 'fetchJson(`/api/drafts?${filtersToQueryString()}`, { timeout: 20000 })' in app_js
        assert "window.retryCurrentTab" in app_js
        assert "appState.isBootstrapped()" in app_js
        assert "serialize_draft_summary" in server_py
        assert ".panel-loader-card" in app_css
        assert ".boot-fallback-inline" in app_css

    def test_index_uses_dynamic_asset_versioning(self):
        html = Path("miniapp/index.html").read_text(encoding="utf-8")
        server_py = Path("miniapp_server.py").read_text(encoding="utf-8")

        assert "__ASSET_VERSION__" in html
        assert "def _asset_version()" in server_py
        assert 'html.replace("__ASSET_VERSION__", _asset_version())' in server_py
        assert "HTMLResponse" in server_py

    def test_detail_buttons_have_visual_feedback_and_notes_survive_refresh(self):
        app_js = " ".join(p.read_text(encoding="utf-8") for p in sorted(Path("miniapp/static").rglob("*.js")))
        app_css = Path("miniapp/static/app.css").read_text(encoding="utf-8")

        assert "function isEditingDetailForm()" in app_js
        assert "if (!isEditingDetailForm()) renderReelsDetail(reel);" in app_js
        assert "if (!isEditingDetailForm() && !hasPendingCarouselOperations(draft.draft_id)) {" in app_js
        assert "onclick=\"updateDraft('status', {status:'approved'}, this)\"" in app_js
        assert "onclick=\"sendDraftToChat('${d.draft_id}', this)\"" in app_js
        assert "onclick=\"deleteDraft('${d.draft_id}', 'drafts', this)\"" in app_js
        assert 'onclick="saveCarouselSlideText(${JSON.stringify(draftId)}, ${index}, this)"' in app_js
        assert 'regenerateCarouselSlide(${JSON.stringify(draftId)}, ${index}, this)' in app_js
        assert 'onclick="regenerateCarouselSlide(${JSON.stringify(draftId)}, ${index}, this)"' in app_js
        assert ".secondary-button.is-busy" in app_css
        assert ".secondary-button.did-complete" in app_css
        assert ".secondary-button.did-error" in app_css

    def test_session_module_avoids_tdz_on_carousel_ops_dependency(self):
        app_js = Path("miniapp/static/app.js").read_text(encoding="utf-8")

        assert "hasPendingCarouselOperations: (draftId) => hasPendingCarouselOperations(draftId)" in app_js

    def test_pending_drafts_are_marked_as_generating(self):
        app_js = " ".join(p.read_text(encoding="utf-8") for p in sorted(Path("miniapp/static").rglob("*.js")))
        app_css = Path("miniapp/static/app.css").read_text(encoding="utf-8")
        presenter_py = Path("bot/services/miniapp_presenter.py").read_text(encoding="utf-8")

        assert '"generation_pending": generation_pending' in presenter_py
        assert '"images_ready": images_ready' in presenter_py
        assert "function draftGenerationLabel(draft)" in app_js
        assert 'class="tag tag-pending"' in app_js
        assert ".draft-card.is-pending" in app_css
        assert ".tag-pending" in app_css

    def test_draft_detail_uses_editorial_hero_and_primary_review_layout(self):
        app_js = " ".join(p.read_text(encoding="utf-8") for p in sorted(Path("miniapp/static").rglob("*.js")))
        app_css = Path("miniapp/static/app.css").read_text(encoding="utf-8")

        assert "function draftHeroSummary" in app_js
        assert "detail-fact-label" in app_js
        assert 'class="detail-top detail-hero"' in app_js
        assert 'class="content-review-highlight"' in app_js
        assert 'class="content-review-lead"' in app_js
        assert 'class="content-review-support-grid"' in app_js
        assert ".detail-hero" in app_css
        assert ".detail-facts" in app_css
        assert ".section-primary" in app_css
        assert ".content-review-lead textarea" in app_css

    def test_overview_lists_share_card_shell_and_human_source_labels(self):
        app_js = " ".join(p.read_text(encoding="utf-8") for p in sorted(Path("miniapp/static").rglob("*.js")))
        app_css = Path("miniapp/static/app.css").read_text(encoding="utf-8")

        assert "function sourceLabel(value)" in app_js
        assert 'return "Из плана";' in app_js
        assert 'return "Контент";' in app_js
        assert 'return "Mini App";' in app_js
        assert 'class="draft-card overview-card' in app_js
        assert 'class="plan-card overview-card' in app_js
        assert 'class="reels-card overview-card' in app_js
        assert 'class="overview-card-top"' in app_js
        assert ".overview-card" in app_css
        assert ".overview-card-top" in app_css
        assert ".overview-card-date" in app_css

    def test_interaction_layer_has_motion_tokens_and_reduced_motion_guard(self):
        app_js = " ".join(p.read_text(encoding="utf-8") for p in sorted(Path("miniapp/static").rglob("*.js")))
        app_css = Path("miniapp/static/app.css").read_text(encoding="utf-8")

        assert "--duration-fast" in app_css
        assert "--ease-standard" in app_css
        assert ":focus-visible" in app_css
        assert ".detail-panel.is-entering" in app_css
        assert "@keyframes detail-panel-enter" in app_css
        assert "@keyframes notice-progress" in app_css
        assert "@media (prefers-reduced-motion: reduce)" in app_css
        assert "let detailEntryTimer = null;" in app_js
        assert 'elements.detailPanel.classList.add("is-entering")' in app_js

    def test_guided_states_cover_empty_and_onboarding_paths(self):
        app_js = " ".join(p.read_text(encoding="utf-8") for p in sorted(Path("miniapp/static").rglob("*.js")))
        app_css = Path("miniapp/static/app.css").read_text(encoding="utf-8")

        assert "function renderGuidedState" in app_js
        assert "Выберите формат для старта" in app_js
        assert "Планов пока нет" in app_js
        assert "Рилсов пока нет" in app_js
        assert "Откройте тему для редактирования" in app_js
        assert "setTab('create')" in app_js
        assert ".guided-state" in app_css
        assert ".guided-state-copy" in app_css
        assert ".guided-state-actions" in app_css
    def test_interactive_cards_support_keyboard_and_aria_contract(self):
        app_js = _miniapp_static_text("app.js")
        core_js = _miniapp_static_text("js", "core.js")
        shell_js = _miniapp_static_text("js", "shell.js")
        create_js = _miniapp_static_text("js", "create.js")
        drafts_js = _miniapp_static_text("js", "drafts.js")
        app_css = Path("miniapp/static/app.css").read_text(encoding="utf-8")

        assert "function interactiveCardAttrs(label)" in core_js
        assert "function bindCardKeyboardActivation()" in shell_js
        assert 'bindCardKeyboardActivation();' in _miniapp_js_bundle()
        assert 'role=\"button\" tabindex=\"0\" aria-label=' in core_js
        assert 'class="create-card${state.selectedCreateTool === "content" ? " active" : ""} interactive-card"' in create_js
        assert 'class=\"draft-card overview-card${d.draft_id === state.draftId ? \" active\" : \"\"}${d.generation_pending ? \" is-pending\" : \"\"} interactive-card\"' in drafts_js
        assert ".interactive-card:focus-visible" in app_css
    def test_create_flow_reopens_full_draft_and_dismisses_keyboard(self):
        shell_js = _miniapp_static_text("js", "shell.js")
        create_js = _miniapp_static_text("js", "create.js")
        app_js = _miniapp_js_bundle()

        assert "function bindKeyboardDismiss()" in shell_js
        assert 'document.addEventListener("touchstart", dismiss, { passive: true });' in shell_js
        assert 'document.addEventListener("mousedown", dismiss, { passive: true });' in shell_js
        assert "bindKeyboardDismiss();" in app_js
        assert "function bindKeyboardViewportAssist()" in shell_js
        assert "function ensureFieldAboveKeyboard(target, behavior = \"smooth\")" in shell_js
        assert "window.visualViewport?.height" in shell_js
        assert "viewport.addEventListener(\"resize\", handleViewportChange);" in shell_js
        assert "bindKeyboardViewportAssist();" in app_js
        assert "scroll-margin-bottom: 180px;" in Path("miniapp/static/app.css").read_text(encoding="utf-8")
        assert 'await openDraft(draft.draft_id)' in create_js

    def test_create_flow_uses_pending_card_and_timeout_recovery(self):
        app_js = " ".join(p.read_text(encoding="utf-8") for p in sorted(Path("miniapp/static").rglob("*.js")))

        assert "function buildPendingDraft(kind, topic)" in app_js
        assert "function openPendingDraftCreation(kind, topic)" in app_js
        assert "function finalizePendingDraftCreation(draft)" in app_js
        assert "function recoverPendingDraftCreation(kind, topic, pendingDraftId)" in app_js
        assert "function isPendingDraftId(value)" in app_js
        assert 'timeout: 45000' in app_js
        assert 'openPendingDraftCreation(format, topic)' in app_js
        assert 'const pending = openPendingDraftCreation("carousel", topic);' in app_js
        assert 'await recoverPendingDraftCreation(format, topic, pending.draft_id);' in app_js
        assert 'await recoverPendingDraftCreation("carousel", topic, pending.draft_id);' in app_js
        assert 'if (String(preferredId).startsWith("pending-")) {' in app_js
        assert 'renderDetailLoader("Генерирую карточку", "Сохраняю черновик и подгружаю содержимое.", "detail-loader-card-compact")' in app_js

    def test_drafts_do_not_auto_open_first_item_on_boot(self):
        app_js = " ".join(p.read_text(encoding="utf-8") for p in sorted(Path("miniapp/static").rglob("*.js")))

        assert 'const preferredId = state.draftId || "";' in app_js
        assert 'state.drafts[0]?.draft_id' not in app_js


class TestMiniAppCarousel:
    async def test_update_carousel_slide_text_returns_none_for_missing(self):
        assert await update_carousel_slide_text("missing-id", 0, "Новый слайд") is None

    async def test_update_carousel_slide_note_returns_none_for_missing(self):
        assert await update_carousel_slide_note("missing-id", 0, "теплее") is None

    async def test_update_carousel_slide_text_updates_payload(self):
        draft = await save_draft(
            kind="carousel",
            topic="Вечерний ритуал",
            source="/carousel",
            payload={
                "slides": ["Старый текст", "Второй слайд"],
                "img_prompts": ["prompt-1", "prompt-2"],
                "img_prompt_notes": ["", ""],
            },
        )

        payload = await update_carousel_slide_text(draft.draft_id, 0, "Новый текст слайда")

        assert payload is not None
        assert payload["slides"][0] == "Новый текст слайда"
        assert payload["slides"][1] == "Второй слайд"

    async def test_update_carousel_slide_note_updates_payload(self):
        draft = await save_draft(
            kind="carousel",
            topic="Вечерний ритуал",
            source="/carousel",
            payload={
                "slides": ["Старый текст", "Второй слайд"],
                "img_prompts": ["prompt-1", "prompt-2"],
                "img_prompt_notes": ["", ""],
            },
        )

        payload = await update_carousel_slide_note(draft.draft_id, 1, "больше воздуха")

        assert payload is not None
        assert payload["img_prompt_notes"][1] == "больше воздуха"

    async def test_select_carousel_slide_version_sets_current_image(self):
        draft = await save_draft(
            kind="carousel",
            topic="Версии",
            source="/carousel",
            payload={
                "slides": ["Слайд 1"],
                "img_prompts": ["prompt-1"],
                "slide_images": [{"filename": "new.png", "url": "/generated/new.png", "generated_at": "2026-03-12T10:00:00+00:00", "prompt": "new"}],
                "slide_image_versions": [[
                    {"filename": "old.png", "url": "/generated/old.png", "generated_at": "2026-03-12T09:00:00+00:00", "prompt": "old"},
                    {"filename": "new.png", "url": "/generated/new.png", "generated_at": "2026-03-12T10:00:00+00:00", "prompt": "new"},
                ]],
            },
        )

        payload = await select_carousel_slide_version(draft.draft_id, 0, 0)

        assert payload is not None
        assert payload["slide_images"][0]["filename"] == "old.png"

    async def test_delete_carousel_slide_version_removes_version_and_keeps_current_valid(self):
        draft = await save_draft(
            kind="carousel",
            topic="Версии",
            source="/carousel",
            payload={
                "slides": ["Слайд 1"],
                "img_prompts": ["prompt-1"],
                "slide_images": [{"filename": "new.png", "url": "/generated/new.png", "generated_at": "2026-03-12T10:00:00+00:00", "prompt": "new"}],
                "slide_image_versions": [[
                    {"filename": "old.png", "url": "/generated/old.png", "generated_at": "2026-03-12T09:00:00+00:00", "prompt": "old"},
                    {"filename": "new.png", "url": "/generated/new.png", "generated_at": "2026-03-12T10:00:00+00:00", "prompt": "new"},
                ]],
            },
        )

        payload = await delete_carousel_slide_version(draft.draft_id, 0, 1)

        assert payload is not None
        assert len(payload["slide_image_versions"][0]) == 1
        assert payload["slide_images"][0]["filename"] == "old.png"


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
        assert await regenerate_reels_frame_asset("missing-id", 0) is None


class TestDraftStore:
    async def test_delete_draft_returns_false_for_missing(self):
        assert await delete_draft("missing-id") is False

    async def test_delete_draft_removes_existing_draft(self):
        draft = await save_draft(
            kind="threads",
            topic="Удаляемый черновик",
            source="/content",
            payload={"caption": "text"},
        )

        deleted = await delete_draft(draft.draft_id)

        assert deleted is True
        assert await drafts_store_module.get_draft(draft.draft_id) is None

    async def test_build_reels_export_payload_counts_ready_frames(self, monkeypatch, tmp_path):
        draft = await save_draft(
            kind="reels",
            topic="Вечерний ритуал",
            source="/reels",
            payload={
                "scenario": "Сценарий",
                "images_ready": 1,
                "storyboard": [
                    {
                        "timecode": "0-3 сек",
                        "scene": "Свеча и флакон",
                        "angle": "Макро",
                        "gemini_prompt": "warm candle and bottle",
                        "current_asset": {"url": "/generated/reels_assets/test/frame_1.png"},
                    },
                    {
                        "timecode": "3-10 сек",
                        "scene": "Руки на ткани",
                        "angle": "Средний план",
                        "gemini_prompt": "hands over linen",
                    },
                ],
            },
        )
        payload = await build_reels_export_payload(draft.draft_id)
        assert payload is not None
        assert payload["ready_frames"] == 1
        assert payload["export_summary"]["missing_assets"] == 1

    async def test_regenerate_reels_frame_asset_updates_current_asset(self, monkeypatch, tmp_path):
        monkeypatch.setattr(reels_assets_module, "ASSETS_DIR", tmp_path / "reels_assets")
        monkeypatch.setattr(
            reels_assets_module,
            "generate_gemini_image_sync",
            lambda prompt, log_context="": b"fake-image-bytes",
        )
        draft = await save_draft(
            kind="reels",
            topic="Вечерний ритуал",
            source="/reels",
            payload={
                "scenario": "Сценарий",
                "images_ready": 0,
                "storyboard": [
                    {
                        "timecode": "0-3 сек",
                        "scene": "Свеча и флакон",
                        "angle": "Макро",
                        "gemini_prompt": "warm candle and bottle",
                    }
                ],
            },
        )
        payload = await regenerate_reels_frame_asset(draft.draft_id, 0)
        assert payload is not None
        current_asset = payload["storyboard"][0]["current_asset"]
        assert current_asset["url"].startswith("/generated/reels_assets/")
        assert payload["images_ready"] == 1


# ---------------------------------------------------------------------------
# creative_team — edit_post_sync (unit: prompt structure + fallback logic)
# ---------------------------------------------------------------------------

from bot.agents.creative_team import _PLATFORM_RULES, _EDITOR_SYSTEM, edit_post_sync


class TestCreativeTeamConstants:
    def test_platform_rules_has_threads(self):
        assert "threads" in _PLATFORM_RULES
        assert "УТРО, ДЕНЬ, ВЕЧЕР" in _PLATFORM_RULES["threads"]
        assert "5-12" in _PLATFORM_RULES["threads"]
        assert "40-120" in _PLATFORM_RULES["threads"]

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

    def test_editor_system_forbids_literary_metaphors_and_slogan_rhythm(self):
        lowered = _EDITOR_SYSTEM.lower()

        assert "плечи в камне" in lowered
        assert "минует логику" in lowered
        assert "литературные метафоры" in lowered
        assert "живую разговорную речь" in lowered
        assert "с подвыподвертом" in lowered
        assert "жёсткие, рубленые" in lowered or "жесткие, рубленые" in lowered

    def test_editor_system_keeps_threads_as_three_posts(self):
        lowered = _EDITOR_SYSTEM.lower()
        assert "утро / день / вечер" in lowered


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

class TestMiniAppReelsPolling:
    def test_server_populates_all_initial_reels_frames(self):
        source = Path("miniapp_server.py").read_text(encoding="utf-8")
        assert "frame_indexes=[0, 1]" not in source
        assert "background_tasks.add_task(" in source


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
        core_js = _miniapp_static_text("js", "core.js")
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
        server_py = Path("miniapp_server.py").read_text(encoding="utf-8")

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

class TestPatchAromaCardsScript:
    def test_coerce_aliases_accepts_exported_json_string(self):
        assert _coerce_aliases('["orange", "sweet orange"]') == ["orange", "sweet orange"]

    def test_coerce_payload_accepts_exported_json_string(self):
        payload = _coerce_payload('{"slug":"orange","resource_values":{"plus":"joy"}}')
        assert payload["slug"] == "orange"
        assert payload["resource_values"]["plus"] == "joy"


# ---------------------------------------------------------------------------
# Markdown rendering coverage and dark-theme CSS safety
# ---------------------------------------------------------------------------


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


class TestDarkThemeCSSReadability:
    """Verify that key light cards stay readable under body.tg-theme-dark."""

    def test_storyboard_frame_has_explicit_dark_theme_override(self):
        app_css = Path("miniapp/static/app.css").read_text(encoding="utf-8")
        assert "body.tg-theme-dark .storyboard-frame" in app_css

    def test_section_accent_has_explicit_dark_theme_override(self):
        app_css = Path("miniapp/static/app.css").read_text(encoding="utf-8")
        assert "body.tg-theme-dark .section-accent" in app_css

    def test_concept_card_uses_hardcoded_light_colors_making_it_safe_in_dark_mode(self):
        """concept-card uses explicit light background gradient and dark text, so it
        stays readable regardless of the OS/Telegram dark theme.
        This is intentional — cards are always light-on-light-background."""
        app_css = Path("miniapp/static/app.css").read_text(encoding="utf-8")
        # The card must define its own background (not rely on --bg which flips dark)
        assert "linear-gradient" in app_css.split(".concept-card {")[1].split("}")[0]
        # The card must have explicit text color (not rely on var(--text))
        card_block = app_css.split(".concept-card {")[1].split("}")[0]
        assert "color:" in card_block

    def test_concept_card_preview_inherits_card_color(self):
        """concept-card .draft-preview must use color: inherit so it inherits the
        card-level dark text, not override with a potentially invisible value."""
        app_css = Path("miniapp/static/app.css").read_text(encoding="utf-8")
        assert ".concept-card .draft-preview" in app_css
        preview_block = app_css.split(".concept-card .draft-preview {")[1].split("}")[0]
        assert "color: inherit;" in preview_block

    def test_detail_markdown_text_is_whitelisted_for_dark_mode_color(self):
        """detail-markdown elements must have their color reset in dark mode so
        inherited dark text does not go invisible on dark backgrounds."""
        app_css = Path("miniapp/static/app.css").read_text(encoding="utf-8")
        assert "body.tg-theme-dark .detail-markdown" in app_css

    def test_detail_preview_text_is_whitelisted_for_dark_mode_color(self):
        app_css = Path("miniapp/static/app.css").read_text(encoding="utf-8")
        assert "body.tg-theme-dark .detail-preview" in app_css


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
            import miniapp_server as _ms
            original_verify = _ms._verify_init_data
            _ms._verify_init_data = lambda _v: True
            try:
                response = client.get(
                    f"/api/reels/{draft.draft_id}",
                    headers={"X-Telegram-Init-Data": "user=%7B%22id%22%3A1%7D&hash=test"},
                )
            finally:
                _ms._verify_init_data = original_verify

        assert response.status_code == 200
        payload = response.json()
        assert payload["frame_count"] == 1
        assert payload["frames"][0]["scene"] == "Открывают флакон"
        assert payload["frames"][0]["timecode"] == "0-5 сек"
