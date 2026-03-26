"""Tests for bot.agents.content_coach — Content Coach Agent."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


# ── Sample data ──────────────────────────────────────────────────────────────

SAMPLE_POST = {
    "pub_id": "test-pub-1",
    "platform": "threads",
    "kind": "carousel",
    "topic": "Лаванда для сна",
    "caption": "Три капли лаванды в диффузор — и засыпаешь за 10 минут.",
    "content_pillar": "essential_oils",
    "funnel_stage": "awareness",
    "likes": 120,
    "comments": 15,
    "shares": 8,
    "saves": 25,
    "views": 2000,
    "score_engagement": 4,
    "score_brand_fit": 5,
    "score_craft": 3,
    "score_goal_hit": 4,
}

TEAM_AVERAGES = {
    "avg_engagement": 3.2,
    "avg_brand": 3.5,
    "avg_craft": 3.0,
    "avg_goal": 3.1,
    "avg_total": 3.2,
}

FORMAT_BENCHMARKS = [
    {"kind": "carousel", "count": 10, "avg_score": 3.5},
    {"kind": "text", "count": 8, "avg_score": 2.8},
    {"kind": "reels", "count": 5, "avg_score": 3.0},
]

PILLAR_BENCHMARKS = [
    {"pillar": "essential_oils", "count": 12, "avg_score": 3.8},
    {"pillar": "meditation", "count": 4, "avg_score": 2.5},
]

SAMPLE_ANALYZE_RESPONSE = {
    "verdict": "success",
    "score_vs_average": 23.5,
    "strengths": [
        "Сильный хук — первое предложение конкретное и понятное",
        "Тема лаванды стабильно показывает высокое вовлечение",
    ],
    "weaknesses": [
        "Нет CTA — пост не конвертирует на следующий шаг",
    ],
    "recommendations": [
        "Добавить вопрос в конце для вовлечения в комментарии",
        "Указать ссылку на полный гайд по маслам",
    ],
    "score_explanation": {
        "engagement": "Выше среднего на 25% — тема резонирует с аудиторией",
        "brand_fit": "Отлично — тон соответствует бренду, нет медицинских обещаний",
        "craft": "На уровне среднего — текст можно сократить",
        "goal_hit": "Выше среднего — пост на awareness, хорошо работает как верх воронки",
    },
    "patterns_detected": [
        "Карусели про лаванду стабильно +30% engagement",
    ],
    "suggested_improvements": "Три капли лаванды в диффузор — и засыпаешь за 10 минут.\n\nА какое масло помогает вам уснуть? Напишите в комментариях.",
}

SAMPLE_SUMMARY_RESPONSE = {
    "top_insight": "Ваши карусели про эфирные масла — лучший формат. Reels отстают на 40%.",
    "format_recommendations": [
        {"format": "carousel", "verdict": "keep", "note": "Стабильно лучший формат"},
        {"format": "reels", "verdict": "improve", "note": "Слабые хуки — первые 3 секунды не цепляют"},
    ],
    "pillar_recommendations": [
        {"pillar": "essential_oils", "verdict": "scale", "note": "+40% vs среднее"},
        {"pillar": "meditation", "verdict": "experiment", "note": "Мало данных, тренд положительный"},
    ],
    "content_gaps": ["Нет контента про звукотерапию — тренд растёт"],
    "weekly_plan_suggestion": "На этой неделе: 2 карусели про масла, 1 reels с улучшенным хуком",
}


# ── Agent tests ──────────────────────────────────────────────────────────────

class TestAnalyzePostPerformance:
    @patch("bot.services.claude_client.call_claude")
    def test_success_verdict(self, mock_call):
        """analyze returns valid structure for a successful post."""
        mock_call.return_value = json.dumps(SAMPLE_ANALYZE_RESPONSE)

        from bot.agents.content_coach import _analyze_sync

        result = _analyze_sync(SAMPLE_POST, TEAM_AVERAGES, FORMAT_BENCHMARKS, PILLAR_BENCHMARKS)

        assert result["verdict"] == "success"
        assert isinstance(result["score_vs_average"], float)
        assert result["score_vs_average"] == 23.5
        assert isinstance(result["strengths"], list)
        assert len(result["strengths"]) > 0
        assert isinstance(result["weaknesses"], list)
        assert isinstance(result["recommendations"], list)
        assert isinstance(result["score_explanation"], dict)
        assert "engagement" in result["score_explanation"]
        assert "brand_fit" in result["score_explanation"]
        assert "craft" in result["score_explanation"]
        assert "goal_hit" in result["score_explanation"]
        assert isinstance(result["patterns_detected"], list)
        assert isinstance(result["suggested_improvements"], str)

    @patch("bot.services.claude_client.call_claude")
    def test_underperformed_verdict(self, mock_call):
        """analyze returns underperformed verdict for weak post."""
        response = dict(SAMPLE_ANALYZE_RESPONSE)
        response["verdict"] = "underperformed"
        response["score_vs_average"] = -25.0
        response["strengths"] = []
        response["weaknesses"] = ["Слабый хук", "Длинный текст"]
        mock_call.return_value = json.dumps(response)

        from bot.agents.content_coach import _analyze_sync

        result = _analyze_sync(SAMPLE_POST, TEAM_AVERAGES, FORMAT_BENCHMARKS, PILLAR_BENCHMARKS)

        assert result["verdict"] == "underperformed"
        assert result["score_vs_average"] == -25.0
        assert len(result["weaknesses"]) == 2

    @patch("bot.services.claude_client.call_claude")
    def test_fallback_on_bad_json(self, mock_call):
        """Returns safe fallback when Claude returns invalid JSON."""
        mock_call.return_value = "This is not valid JSON"

        from bot.agents.content_coach import _analyze_sync

        result = _analyze_sync(SAMPLE_POST, TEAM_AVERAGES, FORMAT_BENCHMARKS, PILLAR_BENCHMARKS)

        assert result["verdict"] == "average"
        assert result["score_vs_average"] == 0.0
        assert isinstance(result["strengths"], list)

    @patch("bot.services.claude_client.call_claude")
    def test_normalizes_invalid_verdict(self, mock_call):
        """Invalid verdict is normalized to 'average'."""
        response = dict(SAMPLE_ANALYZE_RESPONSE)
        response["verdict"] = "amazing"
        mock_call.return_value = json.dumps(response)

        from bot.agents.content_coach import _analyze_sync

        result = _analyze_sync(SAMPLE_POST, TEAM_AVERAGES, FORMAT_BENCHMARKS, PILLAR_BENCHMARKS)

        assert result["verdict"] == "average"

    @patch("bot.services.claude_client.call_claude")
    def test_handles_markdown_wrapped_json(self, mock_call):
        """Handles JSON wrapped in markdown code fences."""
        mock_call.return_value = "```json\n" + json.dumps(SAMPLE_ANALYZE_RESPONSE) + "\n```"

        from bot.agents.content_coach import _analyze_sync

        result = _analyze_sync(SAMPLE_POST, TEAM_AVERAGES, FORMAT_BENCHMARKS, PILLAR_BENCHMARKS)

        assert result["verdict"] == "success"


class TestCoachingSummary:
    @patch("bot.services.claude_client.call_claude")
    def test_summary_structure(self, mock_call):
        """Summary returns valid structure."""
        mock_call.return_value = json.dumps(SAMPLE_SUMMARY_RESPONSE)

        from bot.agents.content_coach import _summary_sync

        result = _summary_sync([SAMPLE_POST], FORMAT_BENCHMARKS, PILLAR_BENCHMARKS)

        assert isinstance(result["top_insight"], str)
        assert len(result["top_insight"]) > 0
        assert isinstance(result["format_recommendations"], list)
        assert isinstance(result["pillar_recommendations"], list)
        assert isinstance(result["content_gaps"], list)
        assert isinstance(result["weekly_plan_suggestion"], str)

    @patch("bot.services.claude_client.call_claude")
    def test_summary_fallback_on_bad_json(self, mock_call):
        """Returns safe fallback when Claude returns invalid JSON."""
        mock_call.return_value = "Not JSON at all"

        from bot.agents.content_coach import _summary_sync

        result = _summary_sync([SAMPLE_POST], FORMAT_BENCHMARKS, PILLAR_BENCHMARKS)

        assert "top_insight" in result
        assert isinstance(result["format_recommendations"], list)


# ── Helper tests ─────────────────────────────────────────────────────────────

class TestHelpers:
    def test_parse_json_plain(self):
        from bot.agents.content_coach import _parse_json

        result = _parse_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_parse_json_markdown_fence(self):
        from bot.agents.content_coach import _parse_json

        result = _parse_json('```json\n{"key": "value"}\n```')
        assert result == {"key": "value"}

    def test_parse_json_invalid(self):
        from bot.agents.content_coach import _parse_json

        result = _parse_json("not json")
        assert result is None

    def test_safe_avg(self):
        from bot.agents.content_coach import _safe_avg

        assert _safe_avg([4, 5, 3, 4]) == 4.0
        assert _safe_avg([None, None]) == 0.0
        assert _safe_avg([4, None, 3]) == 3.5

    def test_find_benchmark(self):
        from bot.agents.content_coach import _find_benchmark

        result = _find_benchmark(FORMAT_BENCHMARKS, "kind", "carousel")
        assert result["avg_score"] == 3.5

        result = _find_benchmark(FORMAT_BENCHMARKS, "kind", "unknown")
        assert result == {}


# ── API endpoint tests ───────────────────────────────────────────────────────

HEADERS = {
    "X-Telegram-Init-Data": "user=%7B%22id%22%3A12345%7D&auth_date=9999999999&hash=abc",
}


@pytest.fixture(autouse=True)
def _bypass_auth(monkeypatch):
    monkeypatch.setenv("AROMA_BYPASS_AUTH", "1")


@pytest.fixture()
async def team_with_publications(setup_test_db):
    from bot.services.team_store import create_team
    from bot.services.past_publications_store import create_publication
    from datetime import datetime, timezone

    team = await create_team("Coach Test Team", creator_telegram_id=12345)

    p1 = await create_publication(
        platform="threads", topic="Post about lavender", kind="carousel",
        caption="Лаванда — удивительное масло для сна",
        likes=120, views=2000, comments=15,
        score_engagement=4, score_brand_fit=5, score_craft=3, score_goal_hit=4,
        content_pillar="essential_oils", funnel_stage="awareness",
        team_id=team.team_id, created_by=12345,
        published_at=datetime(2026, 3, 10, tzinfo=timezone.utc),
    )
    p2 = await create_publication(
        platform="instagram", topic="Meditation guide", kind="reels",
        likes=50, views=800,
        score_engagement=2, score_brand_fit=3, score_craft=2, score_goal_hit=2,
        content_pillar="meditation",
        team_id=team.team_id, created_by=12345,
        published_at=datetime(2026, 3, 15, tzinfo=timezone.utc),
    )
    return team, [p1, p2]


class TestCoachingAPIEndpoints:
    @patch("bot.agents.content_coach._analyze_sync")
    async def test_post_coaching_endpoint(self, mock_analyze, team_with_publications):
        """GET /api/archive/{pub_id}/coaching returns 200 with coaching data."""
        mock_analyze.return_value = SAMPLE_ANALYZE_RESPONSE
        team, pubs = team_with_publications

        from miniapp_server import app

        client = TestClient(app)
        resp = client.get(
            f"/api/archive/{pubs[0].pub_id}/coaching",
            headers={**HEADERS, "X-Team-Id": team.team_id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["verdict"] == "success"
        assert "strengths" in data

    async def test_post_coaching_not_found(self, team_with_publications):
        """GET /api/archive/nonexistent/coaching returns 404."""
        team, _ = team_with_publications

        from miniapp_server import app

        client = TestClient(app)
        resp = client.get(
            "/api/archive/nonexistent/coaching",
            headers={**HEADERS, "X-Team-Id": team.team_id},
        )
        assert resp.status_code == 404

    @patch("bot.agents.content_coach._summary_sync")
    async def test_coaching_summary_endpoint(self, mock_summary, team_with_publications):
        """GET /api/archive/coaching/summary returns 200 with summary data."""
        mock_summary.return_value = SAMPLE_SUMMARY_RESPONSE
        team, _ = team_with_publications

        from miniapp_server import app

        client = TestClient(app)
        resp = client.get(
            "/api/archive/coaching/summary",
            headers={**HEADERS, "X-Team-Id": team.team_id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "top_insight" in data
        assert "format_recommendations" in data

    async def test_coaching_summary_no_publications(self, setup_test_db):
        """GET /api/archive/coaching/summary returns meaningful response with no pubs."""
        from bot.services.team_store import create_team

        team = await create_team("Empty Team", creator_telegram_id=12345)

        from miniapp_server import app

        client = TestClient(app)
        resp = client.get(
            "/api/archive/coaching/summary",
            headers={**HEADERS, "X-Team-Id": team.team_id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "top_insight" in data
        assert "Нет публикаций" in data["top_insight"]
