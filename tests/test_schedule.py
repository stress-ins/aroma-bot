"""Tests for Smart Schedule feature."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


def test_cold_start_defaults():
    from bot.agents.schedule_advisor import COLD_START_SLOTS
    assert len(COLD_START_SLOTS) >= 3
    for slot in COLD_START_SLOTS:
        assert "day" in slot and "hour_utc" in slot and "score" in slot


def test_topic_hint_sleep():
    from bot.agents.schedule_advisor import _get_topic_hint
    hint = _get_topic_hint("Лаванда для сна")
    assert hint is not None
    assert 19 in hint["preferred_hours"] or 20 in hint["preferred_hours"]


def test_topic_hint_morning():
    from bot.agents.schedule_advisor import _get_topic_hint
    hint = _get_topic_hint("Утренний ритуал с маслами")
    assert hint is not None
    assert 6 in hint["preferred_hours"] or 7 in hint["preferred_hours"]


def test_topic_hint_no_match():
    from bot.agents.schedule_advisor import _get_topic_hint
    assert _get_topic_hint("Бергамот в парфюмерии") is None


@pytest.mark.asyncio
async def test_recommend_cold_start():
    from bot.agents.schedule_advisor import recommend_schedule
    result = await recommend_schedule(topic="Лаванда для сна", platform="instagram", team_id=None)
    assert result["cold_start"] is True
    assert len(result["slots"]) == 3
    assert result["topic_hint"] is not None


@pytest.mark.asyncio
async def test_recommend_cold_start_no_topic():
    from bot.agents.schedule_advisor import recommend_schedule
    result = await recommend_schedule(topic="Общая тема", platform="threads", team_id=None)
    assert result["cold_start"] is True
    assert len(result["slots"]) == 3
    assert result["topic_hint"] is None


@pytest.mark.asyncio
async def test_recommend_with_historical():
    from bot.agents.schedule_advisor import recommend_schedule
    mock_times = [
        {"hour": 9, "weekday": 0, "avg_engagement": 85},
        {"hour": 13, "weekday": 2, "avg_engagement": 72},
        {"hour": 19, "weekday": 4, "avg_engagement": 65},
    ]
    with patch("bot.services.social_trends_store.get_best_posting_times", new_callable=AsyncMock, return_value=mock_times):
        result = await recommend_schedule(topic="Масло чайного дерева", platform="instagram", team_id="team_123")
    assert result["cold_start"] is False
    assert len(result["slots"]) == 3


@pytest.mark.asyncio
async def test_recommend_topic_hint_with_historical():
    from bot.agents.schedule_advisor import recommend_schedule
    mock_times = [{"hour": 9, "weekday": 0, "avg_engagement": 50}, {"hour": 19, "weekday": 4, "avg_engagement": 50}]
    with patch("bot.services.social_trends_store.get_best_posting_times", new_callable=AsyncMock, return_value=mock_times):
        result = await recommend_schedule(topic="Сон и лаванда", platform="instagram", team_id="team_123")
    assert result["cold_start"] is False
    assert result["topic_hint"] is not None
    assert "сон" in result["topic_hint"].lower()
