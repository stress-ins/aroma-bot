"""Tests for Trend Radar (Trend Cards) feature."""

from __future__ import annotations

from unittest.mock import patch

import pytest


def test_parse_cards():
    from bot.agents.trend_card_generator import _parse_cards

    raw = """CARD 1:
TITLE: Нероли для сна: тренд или hype?
SUMMARY: Нероли набирает популярность как средство для улучшения сна.
RECOMMENDATION: Создать серию постов о нероли для вечерних ритуалов.
FORMATS: instagram, carousel, reels

CARD 2:
TITLE: Корпоративный wellness растёт
SUMMARY: Компании всё чаще ищут wellness-программы для сотрудников.
RECOMMENDATION: Предложить B2B контент о корпоративных сессиях.
FORMATS: threads_series, instagram"""

    opportunities = [
        {"keyword": "нероли", "score": 0.85, "velocity": 1.2, "lifecycle": "emerging", "sentiment": "positive", "convergence": 0.7, "sources": ["instagram"]},
        {"keyword": "corporate wellness", "score": 0.72, "velocity": 0.8, "lifecycle": "growing", "sentiment": "positive", "convergence": 0.5, "sources": ["google_trends"]},
    ]

    cards = _parse_cards(raw, opportunities)
    assert len(cards) == 2
    assert cards[0]["keyword"] == "нероли"
    assert "Нероли" in cards[0]["title"]
    assert cards[0]["strength"] == 0.85
    assert "instagram" in cards[0]["suggested_formats"]
    assert cards[1]["keyword"] == "corporate wellness"


def test_parse_cards_empty():
    from bot.agents.trend_card_generator import _parse_cards
    cards = _parse_cards("No cards here", [])
    assert cards == []


def test_parse_cards_fills_titles():
    from bot.agents.trend_card_generator import _parse_cards

    raw = """CARD 1:
SUMMARY: Some trend
FORMATS: instagram"""

    opps = [{"keyword": "lavender", "score": 0.5, "velocity": 0, "lifecycle": "", "sentiment": "", "convergence": 0, "sources": []}]
    cards = _parse_cards(raw, opps)
    assert len(cards) == 1
    assert cards[0]["title"] == "Lavender"  # Capitalized keyword as fallback


def test_trend_card_model_exists():
    from db.models import TrendCardModel
    assert hasattr(TrendCardModel, "card_id")
    assert hasattr(TrendCardModel, "keyword")
    assert hasattr(TrendCardModel, "strength")
    assert hasattr(TrendCardModel, "suggested_formats")


def test_repurpose_group_model_exists():
    from db.models import RepurposeGroupModel
    assert hasattr(RepurposeGroupModel, "group_id")
    assert hasattr(RepurposeGroupModel, "source_draft_id")
    assert hasattr(RepurposeGroupModel, "target_drafts")
