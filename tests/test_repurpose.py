"""Tests for Repurpose Engine feature."""

from __future__ import annotations

from unittest.mock import patch

import pytest


def test_extract_core_ideas():
    from bot.agents.repurpose_agent import extract_core_ideas_sync

    response = """CORE: Лаванда помогает регулировать нервную систему через обоняние
POINTS: снижает кортизол; улучшает сон; работает через лимбическую систему
TONE: educational
AUDIENCE: женщины 25-45, интересующиеся wellness"""

    with patch("bot.services.claude_client.call_claude", return_value=response):
        result = extract_core_ideas_sync("Лаванда — удивительное масло.", "Лаванда")

    assert "нервную систему" in result["core_message"]
    assert len(result["key_points"]) == 3
    assert result["tone"] == "educational"
    assert "wellness" in result["target_audience"]


def test_extract_core_ideas_fallback():
    from bot.agents.repurpose_agent import extract_core_ideas_sync

    with patch("bot.services.claude_client.call_claude", return_value="Непарсимый ответ"):
        result = extract_core_ideas_sync("Текст поста.", "Тема")

    assert result["core_message"] == "Текст поста."
    assert result["key_points"] == []


def test_valid_formats():
    from bot.agents.repurpose_agent import VALID_FORMATS
    assert "carousel" in VALID_FORMATS
    assert "reels_v2" in VALID_FORMATS
    assert "threads_series" in VALID_FORMATS


def test_repurpose_group_model():
    from db.models import RepurposeGroupModel
    assert RepurposeGroupModel.__tablename__ == "repurpose_groups"
    assert hasattr(RepurposeGroupModel, "group_id")
    assert hasattr(RepurposeGroupModel, "source_draft_id")
    assert hasattr(RepurposeGroupModel, "core_message")
    assert hasattr(RepurposeGroupModel, "target_drafts")
    assert hasattr(RepurposeGroupModel, "status")
