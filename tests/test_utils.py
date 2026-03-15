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
# TestDraftStore — draft store operations
# ---------------------------------------------------------------------------

from bot.services import drafts_store as drafts_store_module
from bot.services import reels_assets as reels_assets_module
from bot.services.drafts_store import delete_draft
from bot.services.reels_assets import regenerate_reels_frame_asset
from bot.services.miniapp_reels import build_reels_export_payload


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
            lambda prompt, **kwargs: b"fake-image-bytes",
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

    def _mock_brand_settings(self, monkeypatch):
        """Populate brand settings cache for tests."""
        import bot.services.brand_settings_store as bs_mod
        fake = type("FakeBrandSettings", (), {
            "brand_voice": "test voice",
            "forbidden_phrases": ["тазовая волна"],
        })()
        monkeypatch.setattr(bs_mod, "_cache", fake)

    def test_fallback_on_short_result(self, monkeypatch):
        """If Claude returns a very short string, keep original."""
        import bot.agents.creative_team as ct

        self._mock_brand_settings(monkeypatch)

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

        self._mock_brand_settings(monkeypatch)

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


class TestPatchAromaCardsScript:
    def test_coerce_aliases_accepts_exported_json_string(self):
        assert _coerce_aliases('["orange", "sweet orange"]') == ["orange", "sweet orange"]

    def test_coerce_payload_accepts_exported_json_string(self):
        payload = _coerce_payload('{"slug":"orange","resource_values":{"plus":"joy"}}')
        assert payload["slug"] == "orange"
        assert payload["resource_values"]["plus"] == "joy"


# ---------------------------------------------------------------------------
# Dark-theme CSS safety
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Forbidden phrases API + JS/CSS asset checks
# ---------------------------------------------------------------------------

class TestForbiddenPhrasesAPI:
    """Tests for /api/preferences/forbidden-phrases endpoints."""

    def _patch_auth(self, _ms_auth):
        original = _ms_auth._verify_init_data
        _ms_auth._verify_init_data = lambda _v: True
        return original

    def _patch_preload(self, monkeypatch):
        """Prevent lifespan from querying brand_settings table (not available in CI)."""
        import miniapp_server

        async def _noop():
            pass

        monkeypatch.setattr(miniapp_server, "preload_brand_settings", _noop)

    def test_get_forbidden_phrases_returns_defaults(self, tmp_path, monkeypatch):
        """When no custom config file exists, defaults are returned (not empty list)."""
        import miniapp_server
        import miniapp.api.auth as _ms_auth
        monkeypatch.chdir(tmp_path)
        self._patch_preload(monkeypatch)
        original = self._patch_auth(_ms_auth)
        try:
            with TestClient(miniapp_server.app) as client:
                response = client.get(
                    "/api/preferences/forbidden-phrases",
                    headers={"X-Telegram-Init-Data": "user=%7B%22id%22%3A1%7D&hash=test"},
                )
        finally:
            _ms_auth._verify_init_data = original
        assert response.status_code == 200
        data = response.json()
        # PolicyEngine merges defaults when no config file exists
        assert isinstance(data["items"], list)
        assert len(data["items"]) > 0

    def test_add_forbidden_phrase(self, tmp_path, monkeypatch):
        import miniapp_server
        import miniapp.api.auth as _ms_auth
        monkeypatch.chdir(tmp_path)
        self._patch_preload(monkeypatch)
        original = self._patch_auth(_ms_auth)
        try:
            with TestClient(miniapp_server.app) as client:
                response = client.post(
                    "/api/preferences/forbidden-phrases/add",
                    json={"phrase": "тестовая фраза"},
                    headers={"X-Telegram-Init-Data": "user=%7B%22id%22%3A1%7D&hash=test"},
                )
        finally:
            _ms_auth._verify_init_data = original
        assert response.status_code == 200
        assert "тестовая фраза" in response.json()["items"]

    def test_remove_forbidden_phrase(self, tmp_path, monkeypatch):
        import miniapp_server
        import miniapp.api.auth as _ms_auth
        from bot.services.forbidden_phrases import save_forbidden_phrases
        monkeypatch.chdir(tmp_path)
        self._patch_preload(monkeypatch)
        (tmp_path / "data").mkdir()
        save_forbidden_phrases(["фраза для удаления", "другая фраза"])
        original = self._patch_auth(_ms_auth)
        try:
            with TestClient(miniapp_server.app) as client:
                response = client.post(
                    "/api/preferences/forbidden-phrases/remove",
                    json={"phrase": "фраза для удаления"},
                    headers={"X-Telegram-Init-Data": "user=%7B%22id%22%3A1%7D&hash=test"},
                )
        finally:
            _ms_auth._verify_init_data = original
        assert response.status_code == 200
        items = response.json()["items"]
        assert "фраза для удаления" not in items
        assert "другая фраза" in items


class TestForbiddenPhrasesAssets:
    """Smoke checks that JS/CSS assets contain the expected patterns."""

    def test_aroma_card_icon_function_exists_in_app_js(self):
        js = _miniapp_static_text("app.js")
        assert "aromaCardIcon" in js

    def test_dark_mode_concept_card_rule_exists_in_css(self):
        css = _miniapp_static_text("app.css")
        assert "tg-theme-dark .concept-card" in css

    def test_code_block_class_exists_in_css(self):
        css = _miniapp_static_text("app.css")
        assert ".code-block" in css

    def test_forbidden_phrases_section_in_settings_js(self):
        js = _miniapp_static_text("js", "settings.js")
        assert "forbiddenPhrasesList" in js
        assert "addForbiddenPhrase" in js
        assert "removeForbiddenPhrase" in js

    def test_actions_row_pair_class_in_css(self):
        css = _miniapp_static_text("app.css")
        assert "actions-row-pair" in css


class TestHandbookPdfImport:
    """Tests for PDF-imported blends, symptoms, and cross-reference chips."""

    def test_app_js_has_blends_category_meta(self):
        js = _miniapp_js_bundle()
        assert 'id: "blends"' in js
        assert 'label: "Смеси"' in js
        assert 'category: "blend"' in js
        assert 'count: (items) =>' in js

    def test_app_js_has_symptoms_category_meta(self):
        js = _miniapp_js_bundle()
        assert 'id: "symptoms"' in js
        assert 'label: "Симптомы"' in js
        assert 'category: "symptom"' in js

    def test_app_js_handbook_icons_include_blends_and_symptoms(self):
        js = _miniapp_js_bundle()
        assert 'blends: "🌀"' in js
        assert 'symptoms: "🫀"' in js

    def test_references_js_has_cross_ref_chips(self):
        js = _miniapp_js_bundle()
        assert "crossref-chip" in js
        assert "openReference" in js
        assert "zipNamesAndSlugs" in js
        assert "renderCrossRefChips" in js

    def test_references_js_uses_correct_target_tabs(self):
        js = _miniapp_js_bundle()
        # Oil cross-refs link to aromas tab
        assert '"aromas"' in js
        # Blend cross-refs link to blends tab
        assert '"blends"' in js

    def test_app_css_has_crossref_chip_styles(self):
        css = _miniapp_static_text("app.css")
        assert ".crossref-chips" in css
        assert ".crossref-chip" in css
        assert ".crossref-chip--plain" in css

    def test_references_js_symptom_detail_renders_recommended_oils(self):
        js = _miniapp_js_bundle()
        assert "recommended_oil_names" in js
        assert "recommended_oil_slugs" in js
        assert "recommended_blend_names" in js
        assert "Рекомендуемые масла" in js

    def test_references_js_blend_detail_renders_ingredients(self):
        js = _miniapp_js_bundle()
        assert "ingredient_names" in js
        assert "ingredient_slugs" in js
        assert "Состав" in js

    def test_references_js_concept_cards_have_kind_mark(self):
        js = _miniapp_js_bundle()
        assert 'class="concept-kind-mark" aria-hidden="true"' in js
        assert "conceptTypeMeta" in js

    def test_app_css_has_concept_kind_mark_style(self):
        css = _miniapp_static_text("app.css")
        assert ".concept-kind-mark" in css
        assert ".concept-card::before" in css

    def test_references_js_aroma_detail_section_order(self):
        refs_js = _miniapp_static_text("js", "references.js")
        # In the aroma detail view, psychology (now collapsible) and resource sections come before questions
        psychology_index = refs_js.index('renderCollapsibleSection("Психологические свойства", reference.psychological_properties')
        plus_index = refs_js.index('aromaSection(\'Ресурс "+"\', reference.resource_values?.plus)')
        minus_index = refs_js.index('aromaSection(\'Ресурс "-"\', reference.resource_values?.minus)')
        questions_index = refs_js.index('aromaSection("Какие вопросы поднимает", reference.questions)')
        assert psychology_index < plus_index < minus_index < questions_index

    def test_references_js_passport_includes_article_number(self):
        js = _miniapp_js_bundle()
        assert "reference.article_number" in js
        assert '"Артикул"' in js

    def test_search_filter_includes_conditions_and_category_group(self):
        js = _miniapp_js_bundle()
        assert "conditions_for_use" in js
        assert "category_group" in js

    @pytest.mark.asyncio
    async def test_list_reference_cards_blend_returns_items(self, tmp_path):
        import bot.services.miniapp_references as refs
        from db.models import AromaCardModel
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
        from db.models import Base

        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/test.db")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        TestSession = async_sessionmaker(engine, expire_on_commit=False)

        blend_card = AromaCardModel(
            slug="blend-grounding",
            name="Grounding",
            category="blend",
            source_type="blend",
            aliases=["Заземление"],
            payload={"article_number": "#309708", "description": "Баланс и устойчивость"},
        )

        async with TestSession() as session:
            session.add(blend_card)
            await session.commit()

        async def _noop(): pass
        orig_session = refs.AsyncSessionLocal
        orig_seed = refs.seed_reference_cards_if_empty
        try:
            refs.AsyncSessionLocal = TestSession
            refs.seed_reference_cards_if_empty = _noop
            items = await refs.list_reference_cards("blend")
        finally:
            refs.AsyncSessionLocal = orig_session
            refs.seed_reference_cards_if_empty = orig_seed

        assert len(items) == 1
        assert items[0]["slug"] == "blend-grounding"
        assert items[0]["category"] == "blend"

    @pytest.mark.asyncio
    async def test_get_reference_card_blend_returns_payload_fields(self, tmp_path):
        import bot.services.miniapp_references as refs
        from db.models import AromaCardModel
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
        from db.models import Base

        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/test.db")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        TestSession = async_sessionmaker(engine, expire_on_commit=False)

        blend_card = AromaCardModel(
            slug="blend-grounding",
            name="Grounding",
            category="blend",
            source_type="blend",
            aliases=["Заземление"],
            payload={
                "article_number": "#309708",
                "ingredient_names": ["White Spruce", "Vetiver"],
                "ingredient_slugs": ["spruce", "vetiver"],
            },
        )

        async with TestSession() as session:
            session.add(blend_card)
            await session.commit()

        async def _noop(): pass
        orig_session = refs.AsyncSessionLocal
        orig_seed = refs.seed_reference_cards_if_empty
        try:
            refs.AsyncSessionLocal = TestSession
            refs.seed_reference_cards_if_empty = _noop
            card = await refs.get_reference_card("blend", "blend-grounding")
        finally:
            refs.AsyncSessionLocal = orig_session
            refs.seed_reference_cards_if_empty = orig_seed

        assert card is not None
        assert card["slug"] == "blend-grounding"
        assert card["article_number"] == "#309708"
        assert card["ingredient_names"] == ["White Spruce", "Vetiver"]

    def test_concept_and_blend_cards_no_double_icon(self):
        refs_js = _miniapp_static_text("js", "references.js")
        # kind-glyph must be suppressed for concepts and blends (they have icon in badge)
        glyph_line = next(l for l in refs_js.splitlines() if "kind-glyph handbook-glyph" in l)
        assert "concepts" in glyph_line
        assert "blends" in glyph_line

    def test_symptom_cross_ref_chips_have_icons(self):
        refs_js = _miniapp_static_text("js", "references.js")
        assert "SYMPTOM_PARENT_GROUP_ICONS" in refs_js
        assert "related_symptom_parent_groups" in refs_js

    def test_aroma_crossref_blend_names_use_name_ru(self):
        backend = Path("bot/services/miniapp_references.py").read_text(encoding="utf-8")
        # blends_containing_names must use name_ru, not raw blend.name
        assert "name_ru or blend.name" in backend
