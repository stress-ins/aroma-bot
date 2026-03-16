"""Tests for carousel generation, slide building, and MiniApp carousel API."""
from __future__ import annotations

import io
import struct
import zipfile
import zlib

import pytest

from bot.handlers.carousel import (
    _make_slide_prompts_with_text, _make_slide_prompts_no_text,
    _format_for_canva, _build_pptx,
    _generate_slide_image_prompts_sync,
    _embed_font_in_pptx, _FONT_NAME,
)
from bot.agents.carousel_editor import (
    _EDITOR_PROMPT as _CAROUSEL_EDITOR_PROMPT,
    _build_editor_prompt,
    _sanitize_slide_text,
    edit_carousel_sync,
)
from bot.agents.reels_agent import _render_reference_context_block
from bot.services.miniapp_references import build_reference_context
from bot.services.carousel_assets import (
    delete_carousel_slide_version,
    select_carousel_slide_version,
    update_carousel_slide_note,
    update_carousel_slide_text,
)
from bot.services.drafts_store import save_draft


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
        result = _build_pptx(self._SLIDES)
        with zipfile.ZipFile(io.BytesIO(result)) as z:
            # Find at least one slide and verify font name
            slide_files = [n for n in z.namelist() if n.startswith("ppt/slides/slide")]
            assert slide_files, "No slide files found"
            slide_xml = z.read(slide_files[0]).decode()
            assert _FONT_NAME in slide_xml

    def test_with_images(self):
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
        import re
        result = _make_slide_prompts_with_text(_IMG_PROMPTS, _SLIDES)
        # Extract <pre>...</pre> blocks — each must be different
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
        import re
        result = _make_slide_prompts_no_text(_IMG_PROMPTS, _SLIDES)
        blocks = re.findall(r"<pre>(.*?)</pre>", result, re.DOTALL)
        assert len(blocks) == len(_SLIDES)
        assert len(set(blocks)) == len(blocks)

    def test_per_slide_prompt_content_present(self):
        import html as _html
        result = _html.unescape(_make_slide_prompts_no_text(_IMG_PROMPTS, _SLIDES))
        for prompt in _IMG_PROMPTS:
            fragment = prompt.split(",")[0][:20]
            assert fragment in result



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

    def _make_nanobanana_passthrough(self):
        """Return a mock that passes through raw prompts with a prefix."""
        def _fake_optimize(raw_prompt, *, topic, slide_number, total_slides, user_note=""):
            return f"OPTIMIZED_{slide_number}: {raw_prompt}"
        return _fake_optimize

    def test_returns_same_count_as_slides(self, monkeypatch):
        import bot.handlers.carousel as c
        import anthropic as _anthropic
        response = "\n".join(
            f"IMG{i + 1}: unique visual {i + 1}, terracotta, warm light"
            for i in range(len(self._SLIDES_6))
        )
        monkeypatch.setattr(c, "settings", type("s", (), {"anthropic_api_key": "x"})())
        monkeypatch.setattr(_anthropic, "Anthropic", lambda **kw: self._make_fake_client(response)())
        monkeypatch.setattr(
            "bot.agents.nanobanana_prompt_expert.optimize_prompt_for_nanobanana",
            self._make_nanobanana_passthrough(),
        )
        result = c._generate_slide_image_prompts_sync(self._SLIDES_6, "тема")
        assert len(result) == len(self._SLIDES_6)

    def test_prompts_are_unique(self, monkeypatch):
        import bot.handlers.carousel as c
        import anthropic as _anthropic
        response = "\n".join(
            f"IMG{i + 1}: scene_{i + 1} with object_{i + 1}, beige"
            for i in range(len(self._SLIDES_6))
        )
        monkeypatch.setattr(c, "settings", type("s", (), {"anthropic_api_key": "x"})())
        monkeypatch.setattr(_anthropic, "Anthropic", lambda **kw: self._make_fake_client(response)())
        monkeypatch.setattr(
            "bot.agents.nanobanana_prompt_expert.optimize_prompt_for_nanobanana",
            self._make_nanobanana_passthrough(),
        )
        result = c._generate_slide_image_prompts_sync(self._SLIDES_6, "тема")
        assert len(set(result)) == len(result)

    def test_fallback_on_empty_parse(self, monkeypatch):
        """If Claude response is unparseable, fallback strings are returned."""
        import bot.handlers.carousel as c
        import anthropic as _anthropic
        monkeypatch.setattr(c, "settings", type("s", (), {"anthropic_api_key": "x"})())
        monkeypatch.setattr(_anthropic, "Anthropic", lambda **kw: self._make_fake_client("ничего")())
        monkeypatch.setattr(
            "bot.agents.nanobanana_prompt_expert.optimize_prompt_for_nanobanana",
            self._make_nanobanana_passthrough(),
        )
        slides = ["А", "Б"]
        result = c._generate_slide_image_prompts_sync(slides, "тема")
        assert len(result) == 2
        assert all(isinstance(p, str) and len(p) > 10 for p in result)

    def test_nanobanana_expert_called_for_each_slide(self, monkeypatch):
        """Every slide prompt passes through the NanoBanana expert."""
        import bot.handlers.carousel as c
        import anthropic as _anthropic
        response = "\n".join(
            f"IMG{i + 1}: visual {i + 1}, terracotta"
            for i in range(len(self._SLIDES_6))
        )
        monkeypatch.setattr(c, "settings", type("s", (), {"anthropic_api_key": "x"})())
        monkeypatch.setattr(_anthropic, "Anthropic", lambda **kw: self._make_fake_client(response)())
        calls: list[int] = []

        def _tracking_optimize(raw_prompt, *, topic, slide_number, total_slides, user_note=""):
            calls.append(slide_number)
            return f"OPTIMIZED: {raw_prompt}"

        monkeypatch.setattr(
            "bot.agents.nanobanana_prompt_expert.optimize_prompt_for_nanobanana",
            _tracking_optimize,
        )
        result = c._generate_slide_image_prompts_sync(self._SLIDES_6, "тема")
        assert len(calls) == len(self._SLIDES_6)
        for p in result:
            assert p.startswith("OPTIMIZED:")

    def test_prompt_includes_forbidden_visual_motifs(self, monkeypatch):
        import bot.handlers.carousel as c
        from unittest.mock import patch as _patch

        captured: dict[str, str] = {}

        def _fake_call_claude(*, messages, max_tokens, context="", **kw):
            captured["prompt"] = messages[0]["content"]
            return "IMG1: one\nIMG2: two\nIMG3: three\nIMG4: four\nIMG5: five\nIMG6: six"

        def _noop_optimize(raw_prompt, **kw):
            return raw_prompt

        with _patch("bot.services.claude_client.call_claude", side_effect=_fake_call_claude), \
             _patch("bot.agents.nanobanana_prompt_expert.optimize_prompt_for_nanobanana", side_effect=_noop_optimize):
            c._generate_slide_image_prompts_sync(self._SLIDES_6, "тема")
        lowered = captured["prompt"].lower()
        assert "also forbidden everywhere" in lowered
        assert "hands joined together" in lowered
        assert "prayer pose" in lowered


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
