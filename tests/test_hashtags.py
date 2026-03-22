"""Tests for Hashtag Recommender feature."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest


def test_seed_file_valid():
    seed_path = Path(__file__).resolve().parents[1] / "data" / "hashtag_seed.json"
    assert seed_path.exists()
    data = json.loads(seed_path.read_text())
    assert isinstance(data, list)
    assert len(data) >= 80

    for tag in data:
        assert "tag" in tag
        assert "category" in tag
        assert "tier" in tag
        assert tag["tier"] in ("high", "medium", "niche")
        assert "estimated_posts" in tag


def test_seed_has_all_categories():
    seed_path = Path(__file__).resolve().parents[1] / "data" / "hashtag_seed.json"
    data = json.loads(seed_path.read_text())
    categories = {t["category"] for t in data}
    assert "aromatherapy" in categories
    assert "wellness" in categories
    assert "gong_sound" in categories
    assert "body_mind" in categories
    assert "oils" in categories


def test_seed_tier_distribution():
    seed_path = Path(__file__).resolve().parents[1] / "data" / "hashtag_seed.json"
    data = json.loads(seed_path.read_text())
    tiers = {"high": 0, "medium": 0, "niche": 0}
    for t in data:
        tiers[t["tier"]] += 1
    assert tiers["high"] > 0
    assert tiers["medium"] > 0
    assert tiers["niche"] > 0


def test_match_tags():
    from bot.agents.hashtag_recommender import _match_tags

    seed = [
        {"tag": "лаванда", "category": "oils", "tier": "medium", "estimated_posts": 200000},
        {"tag": "lavender", "category": "oils", "tier": "high", "estimated_posts": 5000000},
        {"tag": "стресс", "category": "body_mind", "tier": "high", "estimated_posts": 2000000},
        {"tag": "йога", "category": "practice", "tier": "high", "estimated_posts": 5000000},
    ]
    themes = ["лаванда", "lavender", "стресс"]
    matched = _match_tags(themes, seed)
    assert len(matched) >= 3
    tags = [m["tag"] for m in matched]
    assert "лаванда" in tags
    assert "стресс" in tags


def test_apply_mix_strategy():
    from bot.agents.hashtag_recommender import _apply_mix_strategy

    seed = [
        {"tag": f"high_{i}", "tier": "high", "category": "test"} for i in range(5)
    ] + [
        {"tag": f"medium_{i}", "tier": "medium", "category": "test"} for i in range(5)
    ] + [
        {"tag": f"niche_{i}", "tier": "niche", "category": "test"} for i in range(5)
    ]
    matched = seed  # All matched
    for m in matched:
        m["_score"] = 1

    result = _apply_mix_strategy(matched, seed, count=10)
    tiers = {"high": 0, "medium": 0, "niche": 0}
    for t in result:
        tiers[t["tier"]] += 1

    assert tiers["high"] == 3  # 30%
    assert tiers["medium"] == 4  # 40%
    assert tiers["niche"] == 3  # 30%


def test_get_library():
    from bot.agents.hashtag_recommender import get_library

    all_tags = get_library()
    assert len(all_tags) >= 80

    oils = get_library(category="oils")
    assert all(t["category"] == "oils" for t in oils)

    niche = get_library(tier="niche")
    assert all(t["tier"] == "niche" for t in niche)


def test_recommend_hashtags_sync():
    from bot.agents.hashtag_recommender import recommend_hashtags_sync

    themes_response = "THEME: лаванда | lavender\nTHEME: сон | sleep\nTHEME: релаксация | relaxation"

    with patch("bot.services.claude_client.call_claude", return_value=themes_response):
        result = recommend_hashtags_sync("Лаванда помогает уснуть. Капните 2 капли на подушку.", "instagram", 10)

    assert "hashtags" in result
    assert "mix" in result
    assert "themes" in result
    assert len(result["hashtags"]) <= 10
    assert len(result["themes"]) > 0


def test_extract_themes():
    from bot.agents.hashtag_recommender import _extract_themes_sync

    response = "THEME: ароматерапия | aromatherapy\nTHEME: сон | sleep"

    with patch("bot.services.claude_client.call_claude", return_value=response):
        themes = _extract_themes_sync("Текст про масла", "instagram")

    assert "ароматерапия" in themes
    assert "sleep" in themes
