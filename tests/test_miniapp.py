"""Tests for MiniApp API, presenters, auth, and related services."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from bot.agents.content import ContentDraft
from bot.agents.reels_agent import StoryboardFrame
from bot.services.miniapp_content_review import (
    is_content_review_draft,
    polish_content_review_draft,
    update_content_review_draft,
)
from bot.services.drafts_store import DraftRecord, save_draft
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
from bot.services.miniapp_plans import serialize_plan
from bot.services.miniapp_aromas import get_aroma_card, list_aromas, update_aroma_card
from bot.services.mini_app import build_draft_tab
from bot.handlers.miniapp_bridge import parse_webapp_payload
from bot.services.plans_store import PlanRecord, save_plan
from bot.services.miniapp_references import get_reference_card, list_reference_cards, seed_reference_cards_if_empty
import bot.services.miniapp_references as miniapp_references


def _miniapp_static_text(*relative_parts: str) -> str:
    return Path("miniapp", "static", *relative_parts).read_text(encoding="utf-8")


def _miniapp_js_bundle() -> str:
    return " ".join(p.read_text(encoding="utf-8") for p in sorted(Path("miniapp/static").rglob("*.js")))


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

    def test_payload_preview_threads_series_uses_summary(self):
        preview = payload_preview("threads_series", {
            "series_summary": "Опорная мысль серии про восстановление.",
            "posts": [{"slot": 1, "text": "Утренний пост."}],
        })
        assert "восстановление" in preview

    def test_payload_preview_threads_series_falls_back_to_post(self):
        preview = payload_preview("threads_series", {
            "posts": [{"slot": 1, "text": "Утренний пост серии."}],
        })
        assert "Утренний" in preview

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

    async def test_serialize_draft_exposes_seq_id(self):
        draft = DraftRecord(
            draft_id="seqtest1",
            kind="threads",
            topic="Тест seq_id",
            source="/miniapp",
            created_at="2026-03-13T10:00:00+00:00",
            status="draft",
            feedback="",
            payload={"caption": "Текст"},
            seq_id=42,
        )

        full = await serialize_draft(draft)
        summary = await serialize_draft_summary(draft)

        assert full["seq_id"] == 42
        assert summary["seq_id"] == 42


@pytest.fixture()
def miniapp_test_client(monkeypatch):
    import miniapp_server
    import miniapp.api.auth as _miniapp_auth
    from config import settings as _cfg

    monkeypatch.setattr(_miniapp_auth, "_verify_init_data", lambda _value: True)
    monkeypatch.setattr(_cfg, "anthropic_api_key", "test-key")

    with TestClient(miniapp_server.app) as client:
        yield client


class TestInitDataAuth:
    """Unit tests for _verify_init_data in miniapp.api.auth."""

    def _make_init_data(self, bot_token: str, user_id: int = 1, auth_date: int | None = None) -> str:
        import hashlib
        import hmac
        import time
        import urllib.parse

        if auth_date is None:
            auth_date = int(time.time())
        fields = {"user": f'{{"id":{user_id}}}', "auth_date": str(auth_date)}
        check_string = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
        secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        hash_val = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()
        fields["hash"] = hash_val
        return urllib.parse.urlencode(fields)

    def test_valid_fresh_init_data_passes(self, monkeypatch):
        import miniapp.api.auth as _auth
        monkeypatch.setattr(_auth.settings, "telegram_bot_token", "test-token")
        data = self._make_init_data("test-token")
        assert _auth._verify_init_data(data) is True

    def test_stale_init_data_rejected(self, monkeypatch):
        import time
        import miniapp.api.auth as _auth
        monkeypatch.setattr(_auth.settings, "telegram_bot_token", "test-token")
        stale_date = int(time.time()) - 90000  # 25 hours ago
        data = self._make_init_data("test-token", auth_date=stale_date)
        assert _auth._verify_init_data(data) is False

    def test_wrong_hash_rejected(self, monkeypatch):
        import miniapp.api.auth as _auth
        monkeypatch.setattr(_auth.settings, "telegram_bot_token", "test-token")
        data = self._make_init_data("other-token")  # signed with wrong token
        assert _auth._verify_init_data(data) is False

    def test_bypass_env_skips_all_checks(self, monkeypatch):
        import time
        import miniapp.api.auth as _auth
        monkeypatch.setenv("AROMA_BYPASS_AUTH", "1")
        # stale + wrong hash — still passes when bypass is set
        stale = int(time.time()) - 200000
        data = self._make_init_data("wrong-token", auth_date=stale)
        assert _auth._verify_init_data(data) is True


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

        import miniapp.api.routers.create as _create_router
        monkeypatch.setattr(
            _create_router,
            "complete_content_generation",
            lambda *a, **kw: None,
        )

        response = miniapp_test_client.post(
            "/api/generate/content",
            headers=self.AUTH_HEADERS,
            json={"topic": "Вечерний ритуал", "goal_key": "trust", "format_key": "instagram"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["draft_id"]
        assert payload["kind"] == "instagram"
        assert payload["payload"]["generation_pending"] is True

        detail = miniapp_test_client.get(f"/api/drafts/{payload['draft_id']}", headers=self.AUTH_HEADERS)
        assert detail.status_code == 200
        assert detail.json()["topic"] == "Вечерний ритуал"

    def test_generate_carousel_creates_draft_and_summary(self, miniapp_test_client, monkeypatch):
        import miniapp_server

        async def _noop_complete_carousel_generation(*_args, **_kwargs):
            return None

        import miniapp.api.routers.create as _create_router
        monkeypatch.setattr(_create_router, "complete_carousel_generation", _noop_complete_carousel_generation)

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

        async def _noop_complete_reels_v2_generation(*_args, **_kwargs):
            return None

        import miniapp.api.routers.create as _create_router
        monkeypatch.setattr(_create_router, "complete_reels_v2_generation", _noop_complete_reels_v2_generation)

        response = miniapp_test_client.post(
            "/api/generate/reels",
            headers=self.AUTH_HEADERS,
            json={"topic": "Рилс про паузу", "goal": "trust", "emotion": "calm"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["draft_id"]
        assert payload["generation_pending"] is True
        assert payload["frame_count"] == 0
        assert payload["generation_stage"] == "concept"

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

        import miniapp.api.routers.reels as _reels_router
        monkeypatch.setattr(_reels_router, "regenerate_reels_storyboard", _fake_regenerate_reels_storyboard)
        monkeypatch.setattr(_reels_router, "set_generation_state", _fake_set_generation_state)
        monkeypatch.setattr(_reels_router, "complete_reels_regenerate_all", _fake_complete_reels_regenerate_all)
        monkeypatch.setattr(_reels_router, "serialize_reels_draft", _fake_serialize_reels_draft)

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

        import bot.services.miniapp_references.common as _refs_common
        monkeypatch.setattr(references, "AsyncSessionLocal", lambda: _FakeSessionContext())
        monkeypatch.setattr(references, "seed_reference_cards_if_empty", _noop_seed)
        monkeypatch.setattr(_refs_common, "AsyncSessionLocal", lambda: _FakeSessionContext())
        monkeypatch.setattr(_refs_common, "seed_reference_cards_if_empty", _noop_seed)

        from bot.services.miniapp_references import build_reference_context
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

        import bot.services.miniapp_references.common as _refs_common
        monkeypatch.setattr(references, "AsyncSessionLocal", lambda: _FakeSessionContext())
        monkeypatch.setattr(references, "seed_reference_cards_if_empty", _noop_seed)
        monkeypatch.setattr(_refs_common, "AsyncSessionLocal", lambda: _FakeSessionContext())
        monkeypatch.setattr(_refs_common, "seed_reference_cards_if_empty", _noop_seed)

        from bot.services.miniapp_references import build_reference_context
        result = await build_reference_context(max_items_per_category=2, max_total_chars=220)

        assert result.startswith("Ароматы:")
        assert result.count("- Карточка") <= 2
        assert len(result) <= 220

    def test_generate_plan_returns_entries(self, miniapp_test_client, monkeypatch):
        import miniapp_server
        import analytics.aggregator
        import cache.store

        import miniapp.api.routers.plans as _plans_router
        monkeypatch.setattr(
            _plans_router,
            "generate_plan_sync",
            lambda trends_text, social_trends_text="", own_performance_text="": (
                "📅 Понедельник\n"
                "Платформа: Threads\n"
                "Формат: Пост\n"
                "Цель: Доверие\n"
                "Тема: Тема недели\n"
                "Угол: Через мягкий вход\n"
            ),
        )
        import miniapp.api.routers.plans as _plans_router
        monkeypatch.setattr(_plans_router, "_format_trends", lambda _results: "threads: signal")
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

        import bot.services.drafts_store as _ds
        monkeypatch.setattr(miniapp_server, "_acquire_startup_recovery_lock", lambda: None)
        monkeypatch.setattr(_ds, "list_recent_drafts", _fake_list_recent_drafts)

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
        assert is_valid_content_format("instagram") is True
        assert is_valid_content_format("threads") is False
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
            format_key="instagram",
        )

        assert payload["caption"] == "Текст поста"
        assert payload["slides"] == ["one", "two"]
        assert payload["goal_key"] == "trust"
        assert payload["format_key"] == "instagram"

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
        assert is_content_review_draft("instagram") is True
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
        assert normalize_plan_format({"platform": "Threads", "format_label": "пост"}) == "threads_series"
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


class TestMentionsButtonClasses:
    def test_mentions_detail_uses_correct_button_classes(self):
        mentions_js = Path("miniapp/static/js/mentions.js").read_text()
        assert "primary-button" in mentions_js
        assert "btn btn-primary" not in mentions_js, "should use primary-button, not btn btn-primary"
        assert "btn btn-ghost" not in mentions_js, "should use ghost-button/secondary-button, not btn btn-ghost"
        assert "btn-sm" not in mentions_js, "should use compact, not btn-sm"
        assert "closeMentionDetail" in mentions_js
        assert "showUiNotice" in mentions_js, "mentions module must use showUiNotice for feedback"


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
    def test_index_selects_and_tabs_use_correct_labels(self):
        index_html = Path("miniapp/index.html").read_text(encoding="utf-8")
        app_js = " ".join(p.read_text(encoding="utf-8") for p in sorted(Path("miniapp/static").rglob("*.js")))

        # HTML should have basic structure and mode selectors
        assert 'id="modeContent"' in index_html
        assert 'id="modeHandbook"' in index_html

        # Platform kinds use brand names in JS (RU_KIND_LABELS)
        assert '"Тредс"' in app_js
        assert '"Инстаграм"' in app_js
        assert '"Телеграм"' in app_js
        assert '"Рилсы"' in app_js
        assert '"reels"' in app_js

        # Filter dropdown in index.html uses English brand names
        assert '>Threads<' in index_html
        assert '>Instagram<' in index_html
        assert '>Telegram<' in index_html
        assert '>Reels<' in index_html

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

    def test_create_workspace_format_uses_brand_names(self):
        app_js = " ".join(p.read_text(encoding="utf-8") for p in sorted(Path("miniapp/static").rglob("*.js")))

        # Format selector uses brand names (not Russian transliterations)
        assert "Threads" in app_js
        assert "Instagram" in app_js
        assert "Telegram" in app_js
        # Old Russian transliterations must not appear as option labels
        assert '<option value="threads">Тредс</option>' not in app_js
        assert '<option value="instagram">Инстаграм</option>' not in app_js
        assert '<option value="telegram">Телеграм</option>' not in app_js

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

    async def test_aroma_card_includes_blends_containing_cross_refs(self):
        from datetime import datetime, timezone
        from db.session import AsyncSessionLocal
        from db.models import AromaCardModel

        # Manually insert a blend that contains "orange" so the test is self-contained
        # (blends are seeded via import_handbook_data.py, not via seed_reference_cards_if_empty)
        now = datetime.now(timezone.utc)
        async with AsyncSessionLocal() as session:
            session.add(AromaCardModel(
                category="blend",
                slug="test-blend-a",
                name="Тестовая смесь А",
                source_type="blend",
                aliases=[],
                payload={"ingredient_slugs": ["orange", "lavender"], "ingredient_names": ["Orange", "Lavender"]},
                created_at=now,
                updated_at=now,
            ))
            session.add(AromaCardModel(
                category="blend",
                slug="test-blend-b",
                name="Тестовая смесь Б",
                source_type="blend",
                aliases=[],
                payload={"ingredient_slugs": ["frankincense"], "ingredient_names": ["Frankincense"]},
                created_at=now,
                updated_at=now,
            ))
            await session.commit()

        card = await get_reference_card("aroma", "orange")
        assert card is not None
        assert "blends_containing_names" in card
        assert "blends_containing_slugs" in card
        assert isinstance(card["blends_containing_names"], list)
        assert isinstance(card["blends_containing_slugs"], list)
        # Only test-blend-a contains orange
        assert card["blends_containing_names"] == ["Тестовая смесь А"]
        assert card["blends_containing_slugs"] == ["test-blend-a"]

    async def test_symptom_cross_refs_filters_garbage_and_resolves_aliases(self):
        """_enrich_symptom_cross_refs drops unresolvable/garbage entries and resolves aliases."""
        from bot.services.miniapp_references.symptom import _enrich_symptom_cross_refs, _is_garbage_name
        from datetime import datetime, timezone
        from sqlalchemy import select
        from db.session import AsyncSessionLocal
        from db.models import AromaCardModel

        now = datetime.now(timezone.utc)
        async with AsyncSessionLocal() as session:
            # Ensure we have aroma cards for alias resolution tests
            for slug, name, name_ru in [
                ("sacred-frankincense", "Sacred Frankincense", "Священный ладан"),
                ("frankincense", "Frankincense", "Ладан"),
                ("basil", "Basil", "Базилик"),
                ("cypress", "Cypress", "Кипарис"),
                ("myrrh", "Myrrh", "Мирра"),
            ]:
                existing = await session.execute(
                    select(AromaCardModel).where(
                        AromaCardModel.slug == slug,
                        AromaCardModel.category == "aroma",
                    )
                )
                if not existing.scalar_one_or_none():
                    session.add(AromaCardModel(
                        category="aroma",
                        slug=slug,
                        name=name,
                        source_type="resin",
                        aliases=[],
                        payload={"name_ru": name_ru},
                        created_at=now,
                        updated_at=now,
                    ))
            # Add a blend card to test blend redirection
            existing_blend = await session.execute(
                select(AromaCardModel).where(
                    AromaCardModel.slug == "valor",
                    AromaCardModel.category == "blend",
                )
            )
            if not existing_blend.scalar_one_or_none():
                session.add(AromaCardModel(
                    category="blend",
                    slug="valor",
                    name="Valor",
                    source_type="blend",
                    aliases=[],
                    payload={"name_ru": "Вэлор"},
                    created_at=now,
                    updated_at=now,
                ))
            await session.commit()

        serialized: dict[str, object] = {
            "recommended_oil_names": [
                "Sacred Frankincense",       # alias → sacred-frankincense
                "РЕКОМЕНДАЦИИ",              # garbage header
                "wk",                        # too short
                "(Священный ладан)",         # starts with (
                "Valor",                     # blend, not oil
                "Dorado Azul",               # no card in DB → dropped
                "Frankincense",              # direct match
                "Basil",                     # new alias → basil
                "Cypress",                   # new alias → cypress
                "Мирра",                     # Russian alias → myrrh
                "wk Copaiba",                # OCR prefix → garbage
                "чк Clove",                  # OCR prefix → garbage
            ],
            "recommended_oil_slugs": [],     # no pre-resolved slugs
            "recommended_blend_names": [],
            "recommended_blend_slugs": [],
        }

        result = await _enrich_symptom_cross_refs(serialized)

        # Sacred Frankincense now maps to its own card, Frankincense separate
        assert "sacred-frankincense" in result["recommended_oil_slugs"]
        assert "frankincense" in result["recommended_oil_slugs"]
        # New aliases should resolve
        assert "basil" in result["recommended_oil_slugs"]
        assert "cypress" in result["recommended_oil_slugs"]
        assert "myrrh" in result["recommended_oil_slugs"]
        # Valor should have been redirected to blend list
        assert "valor" in result["recommended_blend_slugs"]
        # OCR garbage should not appear
        assert all(s not in result["recommended_oil_names"] for s in ["wk Copaiba", "чк Clove"])

        # Verify garbage filter directly
        assert _is_garbage_name("wk") is True
        assert _is_garbage_name("РЕКОМЕНДАЦИИ по применению") is True
        assert _is_garbage_name("(Священный ладан)") is True
        assert _is_garbage_name("Иланг-иланг)") is True
        assert _is_garbage_name("Lavender") is False
        assert _is_garbage_name("Tea Tree") is False
        # New OCR prefix patterns
        assert _is_garbage_name("wk Copaiba") is True
        assert _is_garbage_name("чк Clove") is True
        assert _is_garbage_name("^k Fennel") is True
        assert _is_garbage_name("k Cistus") is True
        assert _is_garbage_name("i Rosemary") is True
        assert _is_garbage_name("~ Lavender") is True
        # Russian sentences (long, starts lowercase)
        assert _is_garbage_name("применять наружно на область грудной клетки") is True
        # Short valid names should pass
        assert _is_garbage_name("Dill") is False
        assert _is_garbage_name("Basil") is False

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
        import bot.services.miniapp_references.common as _refs_common
        monkeypatch.setattr(_refs_common, "SEED_FILE", seed_file)
        monkeypatch.setattr(_refs_common, "EXTRA_SEED_FILE", extra_seed_file)

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

    def test_merge_seed_preserves_complementary_oil_fields(self):
        """_merge_seed_into_existing must keep complementary_oil_names/slugs from DB."""
        from bot.services.miniapp_references.common import _merge_seed_into_existing

        existing_payload = {
            "category": "oil",
            "slug": "lavender",
            "name": "Лаванда",
            "complementary_oil_names": ["Мята", "Розмарин"],
            "complementary_oil_slugs": ["mint", "rosemary"],
            "name_en": "Lavender",
        }
        seed_payload = {
            "category": "oil",
            "slug": "lavender",
            "name": "Лаванда обновлённая",
        }

        merged = _merge_seed_into_existing(existing_payload, seed_payload)
        assert merged["complementary_oil_names"] == ["Мята", "Розмарин"]
        assert merged["complementary_oil_slugs"] == ["mint", "rosemary"]
        assert merged["name_en"] == "Lavender"
        # seed name should win (not an enrichment field)
        assert merged["name"] == "Лаванда обновлённая"

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
        assert 'if (!appState.isBootstrapped()) {' in runtime_js
        assert 'appState.setBootstrapped(true)' in runtime_js
        # Bootstrap shows UI immediately via app-ready + safeLoadCurrentTab
        assert 'void safeLoadCurrentTab(' in runtime_js

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
        assert 'id="btnTabSettings"' in html

    def test_handbook_concepts_have_meta_and_render_course_fields(self):
        app_js = " ".join(p.read_text(encoding="utf-8") for p in sorted(Path("miniapp/static").rglob("*.js")))
        app_css = Path("miniapp/static/app.css").read_text(encoding="utf-8")

        assert 'category: "concept"' in app_js
        assert 'searchLabel: "Поиск темы"' in app_js
        assert "COURSE_NAMES" in app_js  # human-readable course source labels
        assert 'function conceptTypeMeta(sourceType)' in app_js
        assert 'founder:   { label: "Автор",   icon: "👤" }' in app_js
        assert 'chakra:    { label: "Чакра",   icon: "🔮" }' in app_js
        assert 'archetype: { label: "Архетип", icon: "✧" }' in app_js
        assert 'class="draft-card overview-card' in app_js
        assert 'class="kind-glyph handbook-glyph" aria-hidden="true"' in app_js
        assert 'tone-${escapeHtml(item.tone)}' in app_js
        assert 'reference-hero-card is-theory' in app_js
        assert 'reference-card${state.tab === "concepts" ? " is-theory concept-card" : ""}' in app_js
        assert 'reference.chakra_focus && { icon: "✦", label: "Чакры", value: reference.chakra_focus }' in app_js
        assert 'reference.course_source && { icon: "📚", label: "Курс", value: formatCourseSourceLabel(reference.course_source) }' in app_js
        assert '${aromaSection("Материалы курса", reference.course_notes)}' in app_js
        assert ".reference-card .overview-card-date" in app_css
        assert ".reference-hero-card.is-theory" in app_css
        assert ".reference-badge.tone-course" in app_css
        assert ".concept-kind-mark" in app_css
        assert ".concept-card::before" in app_css

    def test_content_detail_supports_prompt_copy_actions(self):
        app_js = " ".join(p.read_text(encoding="utf-8") for p in sorted(Path("miniapp/static").rglob("*.js")))

        assert "Скопировать промпт слайда" in app_js
        assert "function copyText" in app_js
        assert "function togglePromptDisclosure" in app_js
        assert "state.openPromptPanels" in app_js
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
        assert "contentKindIcon" in app_js

    def test_telegram_dark_theme_uses_body_class_for_bottom_nav(self):
        source = " ".join(p.read_text(encoding="utf-8") for p in sorted(Path("miniapp/static").rglob("*.js")))
        app_css = Path("miniapp/static/app.css").read_text(encoding="utf-8")

        assert 'document.body.classList.toggle("tg-theme-dark", tg.colorScheme === "dark");' in source
        assert "body.tg-theme-dark .bottom-tab-bar-inner" in app_css
        assert ".concept-card .draft-preview" in app_css
        assert "color: inherit;" in app_css
        assert "contentKindIcon" in source
        assert 'iconMap[normalized] || "note"' in source

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

    def test_mobile_shell_moves_primary_navigation_to_bottom_bar(self):
        app_css = Path("miniapp/static/app.css").read_text(encoding="utf-8")
        html = Path("miniapp/index.html").read_text(encoding="utf-8")

        # On mobile the topbar-main is now sticky (shows section title) rather than hidden;
        # primary tab navigation still lives in the bottom bar.
        assert 'body.is-mobile-layout .topbar-main {' in app_css
        assert 'position: sticky' in app_css
        # "Планы" tab moved into content sub-tabs; bottom bar has 4 buttons now
        expected_order = [
            'id="btnTabInspiration"',
            'id="btnTabCreate"',
            'id="btnTabHandbook"',
            'id="btnTabSettings"',
        ]
        positions = [html.index(marker) for marker in expected_order]
        assert positions == sorted(positions)
        assert 'data-tab="settings"' in html

    def test_safe_area_insets_protect_content_from_telegram_chrome_and_dynamic_island(self):
        """Content and interactive buttons must not be hidden under the
        Dynamic Island, iPhone notch, or Telegram WebApp chrome (close/nav bar).

        Requirements:
        - viewport-fit=cover in HTML so env(safe-area-inset-*) works in WKWebView
        - env(safe-area-inset-top) applied on shell/body so top content starts below
          Dynamic Island / Telegram close button — no useful content or buttons hidden
        - env(safe-area-inset-bottom) applied on bottom tab bar so tab buttons stay
          above the iPhone home indicator bar
        - In detail view, the back button must be sticky below the safe inset
        - session.js must apply TG_HEADER_FALLBACK so content doesn't go under
          Telegram header on older Bot API versions without contentSafeAreaInset
        """
        app_css = Path("miniapp/static/app.css").read_text(encoding="utf-8")
        html = Path("miniapp/index.html").read_text(encoding="utf-8")
        session_js = Path("miniapp/static/js/session.js").read_text(encoding="utf-8")
        shell_js = Path("miniapp/static/js/shell.js").read_text(encoding="utf-8")

        # Required for env(safe-area-inset-*) to work inside WKWebView / Telegram
        assert "viewport-fit=cover" in html

        # Top safe area — prevents content/buttons from being hidden under
        # Dynamic Island (iPhone 14 Pro+) or Telegram's Close button chrome
        assert "env(safe-area-inset-top" in app_css

        # Bottom safe area — prevents bottom tab buttons from sitting under
        # the iPhone home indicator bar or Telegram bottom chrome
        assert "env(safe-area-inset-bottom" in app_css

        # The bottom tab bar itself must apply the bottom inset
        tab_bar_css = app_css.split(".bottom-tab-bar", 1)[1] if ".bottom-tab-bar" in app_css else ""
        assert "safe-area-inset-bottom" in tab_bar_css

        # Safe zone: --tg-content-inset-top custom prop must be used in CSS
        # for BOTH the shell top padding AND the sticky back button position
        assert "--tg-content-inset-top" in app_css

        # Back button in detail view must stick right at the safe inset, not buried
        detail_view_section = app_css.split("is-detail-view", 1)[1] if "is-detail-view" in app_css else ""
        assert "tg-content-inset-top" in detail_view_section, (
            "Back button in is-detail-view must have top: var(--tg-content-inset-top...) "
            "so it stays below Telegram chrome"
        )

        # session.js must include TG_HEADER_FALLBACK so older Telegram versions
        # without contentSafeAreaInset still reserve space for the Telegram header bar
        assert "TG_HEADER_FALLBACK" in session_js, (
            "session.js must define TG_HEADER_FALLBACK (fallback for older Telegram versions "
            "that don't expose contentSafeAreaInset.top covering the TG header bar)"
        )
        assert "contentSafeAreaInset" in session_js, (
            "session.js must read contentSafeAreaInset.top for Bot API 8.0+ full chrome height"
        )

        # goBackToList in shell.js must not call BackButton.hide() before checking _fromContext
        # (cross-tab navigation back must work without hiding the TG back button prematurely)
        assert "_fromContext" in shell_js

    def test_prompt_disclosure_state_uses_isPromptDisclosureOpen_in_carousel_and_reels(self):
        """Prompt disclosure panels must use isPromptDisclosureOpen() so their open/closed
        state survives polling refreshes without resetting."""
        carousel_js = Path("miniapp/static/js/carousel.js").read_text(encoding="utf-8")
        reels_js = Path("miniapp/static/js/reels.js").read_text(encoding="utf-8")

        # carousel.js must declare isPromptDisclosureOpen in deps destructuring
        assert "isPromptDisclosureOpen," in carousel_js
        # carousel.js must call isPromptDisclosureOpen for its disclosure key
        assert "isPromptDisclosureOpen(`carousel:" in carousel_js

        # reels.js must declare isPromptDisclosureOpen in deps destructuring
        assert "isPromptDisclosureOpen," in reels_js
        # reels.js: V1 prompt disclosure was removed; V2 uses inline frame editing
        # Just verify the dep is still declared (may be used by future frame editors)
        assert "isPromptDisclosureOpen" in reels_js

        # app.js must pass isPromptDisclosureOpen to both module factories
        app_js = Path("miniapp/static/app.js").read_text(encoding="utf-8")
        carousel_block = app_js[app_js.index("createCarouselModule("):app_js.index("createCarouselModule(") + 600]
        reels_block = app_js[app_js.index("createReelsModule("):app_js.index("createReelsModule(") + 600]
        assert "isPromptDisclosureOpen," in carousel_block
        assert "isPromptDisclosureOpen," in reels_block

    def test_reels_opened_from_drafts_route_into_storyboard_detail(self):
        drafts_js = _miniapp_static_text("js", "drafts.js")

        assert 'kind === "reels"' in drafts_js and 'kind === "reels_v2"' in drafts_js
        assert "await callbacks.openReels(d.draft_id);" in drafts_js

    def test_carousel_detail_uses_actions_instead_of_raw_json(self):
        app_js = " ".join(p.read_text(encoding="utf-8") for p in sorted(Path("miniapp/static").rglob("*.js")))
        server_py = Path("miniapp_server.py").read_text(encoding="utf-8") + "".join(
            p.read_text(encoding="utf-8") for p in sorted(Path("miniapp/api").rglob("*.py"))
        )

        assert "JSON</h3>" not in app_js
        assert "Обновить все слайды" in app_js
        assert "Обновить по замечанию" in app_js
        assert "Сохранить текст слайда" in app_js
        assert "Подпись слайда" in app_js
        assert "downloadCarouselPptx" in app_js
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
        server_py = Path("miniapp_server.py").read_text(encoding="utf-8") + "".join(
            p.read_text(encoding="utf-8") for p in sorted(Path("miniapp/api").rglob("*.py"))
        )

        # V2 reels editing actions
        assert "Перегенерировать концепцию" in app_js
        assert "Перегенерировать сценарий" in app_js
        assert "Перегенерировать раскадровку" in app_js
        assert "Согласовать" in app_js
        assert "Сохранить замечания" in app_js
        assert "/api/reels/{draft_id}/scenario" in server_py
        assert "/api/reels/{draft_id}/storyboard/regenerate" in server_py
        assert "/api/reels/{draft_id}/frames/regenerate-all" in server_py
        assert "/api/reels/{draft_id}/frames/{frame_index}/fields" in server_py
        assert "/api/reels/{draft_id}/force-edit" in server_py

    def test_content_review_detail_supports_editing_polish_and_feedback(self):
        app_js = " ".join(p.read_text(encoding="utf-8") for p in sorted(Path("miniapp/static").rglob("*.js")))
        app_css = Path("miniapp/static/app.css").read_text(encoding="utf-8")
        server_py = Path("miniapp_server.py").read_text(encoding="utf-8") + "".join(
            p.read_text(encoding="utf-8") for p in sorted(Path("miniapp/api").rglob("*.py"))
        )

        assert "function isContentReviewKind" in app_js
        assert "Редактор" in app_js
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
        assert "Создать рилс" in app_js
        assert "Собрать карусель" in app_js
        assert "Тема материала" in app_js
        assert "Опорная мысль" in app_js
        assert "Первая фраза" in app_js
        assert "Призыв к действию" in app_js
        assert "Промпт для визуала" in app_js
        assert "Согласовать" in app_js
        assert "Вернуть на доработку" in app_js
        assert "В чат" in app_js
        assert "deleteDraft" in app_js

    def test_keywords_detail_supports_editing_and_ui_notices(self):
        app_js = " ".join(p.read_text(encoding="utf-8") for p in sorted(Path("miniapp/static").rglob("*.js")))
        app_css = Path("miniapp/static/app.css").read_text(encoding="utf-8")
        server_py = Path("miniapp_server.py").read_text(encoding="utf-8") + "".join(
            p.read_text(encoding="utf-8") for p in sorted(Path("miniapp/api").rglob("*.py"))
        )

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
        assert 'title: "Публикаций пока нет"' in app_js
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
        assert ".tab-button," in app_css
        assert ".mode-button," in app_css
        assert ".back-button," in app_css

    def test_section_titles_have_russian_translations_for_all_handbook_tabs(self):
        app_js = Path("miniapp/static/app.js").read_text(encoding="utf-8")
        assert '"blends": "Смеси"' in app_js or "'blends': \"Смеси\"" in app_js or "blends: \"Смеси\"" in app_js
        assert '"symptoms": "Симптомы"' in app_js or "symptoms: \"Симптомы\"" in app_js
        # Ensure the fallback `?? t` is not hit for any known handbook tab
        for tab_key in ("aromas", "concepts", "practices", "sounds", "blends", "symptoms"):
            assert f'{tab_key}:' in app_js or f'"{tab_key}":' in app_js, f"SECTION_TITLES missing key: {tab_key}"

    def test_draft_detail_supports_reject_and_delete_actions(self):
        app_js = " ".join(p.read_text(encoding="utf-8") for p in sorted(Path("miniapp/static").rglob("*.js")))
        server_py = Path("miniapp_server.py").read_text(encoding="utf-8") + "".join(
            p.read_text(encoding="utf-8") for p in sorted(Path("miniapp/api").rglob("*.py"))
        )
        html = Path("miniapp/index.html").read_text(encoding="utf-8")

        assert "Вернуть на доработку" in app_js
        assert 'title="Вернуть на доработку"' in app_js
        assert 'actionLabel("trash"' in app_js
        assert "deleteDraft" in app_js
        assert "rejected" in app_js
        assert '@router.delete("/api/drafts/{draft_id}")' in server_py
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
        server_py = Path("miniapp_server.py").read_text(encoding="utf-8") + "".join(
            p.read_text(encoding="utf-8") for p in sorted(Path("miniapp/api").rglob("*.py"))
        )

        assert "function renderPanelLoader" in app_js
        assert "function renderPanelError" in app_js
        assert 'elements.draftList.innerHTML = renderPanelLoader("Загружаю раздел")' in app_js
        assert 'message === "request_timeout"' in app_js
        assert 'fetchJson(`/api/drafts?${filtersToQueryString()}&include_metrics=true`, { timeout: 20000 })' in app_js
        assert "window.retryCurrentTab" in app_js
        assert "appState.isBootstrapped()" in app_js
        assert "serialize_draft_summary" in server_py
        assert ".panel-loader-card" in app_css
        assert ".boot-fallback-inline" in app_css

    def test_index_uses_dynamic_asset_versioning(self):
        html = Path("miniapp/index.html").read_text(encoding="utf-8")
        server_py = Path("miniapp_server.py").read_text(encoding="utf-8") + "".join(
            p.read_text(encoding="utf-8") for p in sorted(Path("miniapp/api").rglob("*.py"))
        )

        assert "__ASSET_VERSION__" in html
        assert "def _asset_version()" in server_py
        assert 'html.replace("__ASSET_VERSION__", _asset_version())' in server_py
        assert "HTMLResponse" in server_py

    def test_detail_buttons_have_visual_feedback_and_notes_survive_refresh(self):
        app_js = " ".join(p.read_text(encoding="utf-8") for p in sorted(Path("miniapp/static").rglob("*.js")))
        app_css = Path("miniapp/static/app.css").read_text(encoding="utf-8")

        assert "function isEditingDetailForm()" in app_js
        assert "if (!isEditingDetailForm()) renderReelsDetail(reel);" in app_js
        assert "!isEditingDetailForm() && !detailHasFocus && !hasPendingCarouselOperations(draft.draft_id)" in app_js
        assert 'data-action="updateDraft"' in app_js
        assert '{"status":"approved"}' in app_js
        assert '{"status":"rejected"}' in app_js
        assert 'data-action="deleteDraft"' in app_js
        assert 'data-action="saveCarouselSlideText"' in app_js
        assert 'data-action="regenerateCarouselSlide"' in app_js
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
        assert 'if (normalized === "/miniapp") return "";' in app_js
        assert 'class="draft-card overview-card' in app_js
        assert 'class="plan-card plan-card-' in app_js
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
        assert "Публикаций пока нет" in app_js
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
        assert 'isSeries ? "Генерирую серию" : "Генерирую карточку"' in app_js
        assert '"Сохраняю черновик и подгружаю содержимое."' in app_js
        assert '"detail-loader-card-compact"' in app_js

    def test_drafts_do_not_auto_open_first_item_on_boot(self):
        app_js = " ".join(p.read_text(encoding="utf-8") for p in sorted(Path("miniapp/static").rglob("*.js")))

        assert 'const preferredId = state.draftId || "";' in app_js
        assert 'state.drafts[0]?.draft_id' not in app_js

    def test_render_structured_list_pdf_artifacts(self):
        """renderStructuredList handles z-bullets, page numbers and hyphen-splits."""
        js = Path("miniapp/static/js/references.js").read_text(encoding="utf-8")
        assert "z\\s+" in js        # z-bullet normalization
        assert r"/^\d{1,3}$/" in js  # page number stripping
        assert 'result.endsWith("-")' in js  # hyphen-join

    def test_drafts_api_uses_newest_first_ordering(self):
        """API должен запрашивать черновики новейшими первыми."""
        src = Path("miniapp/api/routers/drafts.py").read_text(encoding="utf-8")
        assert "newest_first=True" in src

    def test_content_polish_uses_asyncio_to_thread(self):
        """polish_content_review_draft не должен блокировать event loop."""
        src = Path("bot/services/miniapp_content_review.py").read_text(encoding="utf-8")
        assert "asyncio.to_thread" in src

    def test_content_agent_uses_get_running_loop(self):
        """content.py должен использовать get_running_loop, не get_event_loop."""
        src = Path("bot/agents/content.py").read_text(encoding="utf-8")
        assert "get_event_loop" not in src
        assert "get_running_loop" in src or "asyncio.to_thread" in src


class TestIconMappings:
    """Guard tests: every icon name used in JS must have a LUCIDE_MAP entry."""

    def _parse_lucide_map_keys(self) -> set[str]:
        """Extract all keys from LUCIDE_MAP in app.js."""
        import re
        src = _miniapp_static_text("app.js")
        # Find LUCIDE_MAP block
        m = re.search(r"const LUCIDE_MAP\s*=\s*\{(.*?)\};", src, re.DOTALL)
        assert m, "LUCIDE_MAP not found in app.js"
        block = m.group(1)
        # Extract keys: either bare identifiers or quoted strings
        keys = set()
        for km in re.finditer(r'(?:^|,)\s*(?:"([^"]+)"|\'([^\']+)\'|(\w[\w-]*))\s*:', block):
            keys.add(km.group(1) or km.group(2) or km.group(3))
        return keys

    def _find_used_icon_names(self) -> set[str]:
        """Find all icon names passed to uiIcon() and actionLabel() across JS files."""
        import re
        bundle = _miniapp_js_bundle()
        names: set[str] = set()
        for fn in ("uiIcon", "actionLabel"):
            for m in re.finditer(rf'{fn}\(\s*["\']([^"\']+)["\']', bundle):
                names.add(m.group(1))
        return names

    def test_all_icon_names_have_lucide_mapping(self):
        """Every icon name referenced in uiIcon/actionLabel must exist in LUCIDE_MAP."""
        lucide_keys = self._parse_lucide_map_keys()
        used_names = self._find_used_icon_names()
        missing = used_names - lucide_keys
        assert not missing, (
            f"Icon names used but missing from LUCIDE_MAP: {sorted(missing)}. "
            f"Add them to LUCIDE_MAP in miniapp/static/app.js"
        )

    def test_no_square_terminal_fallback_in_rendered_html(self):
        """No JS file should hard-code square-terminal except as the prompt icon mapping."""
        import re
        bundle = _miniapp_js_bundle()
        # Remove the LUCIDE_MAP prompt entry — that's intentional
        # Remove the LUCIDE_MAP prompt entry and the fallback line — both intentional
        cleaned = re.sub(r'prompt:\s*"square-terminal"', '', bundle)
        cleaned = re.sub(r'LUCIDE_MAP\[name\]\s*\|\|\s*"square-terminal"', '', cleaned)
        assert 'square-terminal' not in cleaned, (
            "Found 'square-terminal' outside of LUCIDE_MAP prompt entry — "
            "likely a fallback icon is being used where a proper mapping should exist"
        )


class TestSuggestTopics:
    def test_suggest_topics_prompt_excludes_used(self):
        from bot.agents.content import _suggest_topics_prompt
        prompt = _suggest_topics_prompt("trust", "instagram", ["Тема A", "Тема B"])
        assert "НЕ повторяй темы похожие на" in prompt
        assert "Тема A" in prompt and "Тема B" in prompt
        assert "5 тем" in prompt

    def test_suggest_topics_prompt_without_exclusions(self):
        from bot.agents.content import _suggest_topics_prompt
        prompt = _suggest_topics_prompt("trust", "instagram", [])
        assert "НЕ повторяй" not in prompt
        assert "5 тем" in prompt

    def test_create_forms_have_suggest_button(self):
        from pathlib import Path
        create_js = Path("miniapp/static/js/create.js").read_text(encoding="utf-8")
        assert "suggest-topic-btn" in create_js
        assert "bindSuggestButton" in create_js

    def test_threads_caption_fallback_when_no_caption_parsed(self):
        from bot.agents.content import parse_content_draft, _has_structured_content
        raw = "УТРО\nТекст.\n\nДЕНЬ\nТекст.\n\nВЕЧЕР\nТекст.\n\nVISUAL_PROMPT: soft light"
        draft = parse_content_draft(raw)
        assert draft.visual_prompt
        assert _has_structured_content(draft)
        assert not draft.caption
