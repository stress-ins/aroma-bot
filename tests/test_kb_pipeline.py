"""Tests for KB Quality Pipeline — medical_reviewer + kb_pipeline phases."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


# ─── medical_reviewer tests ───────────────────────────────────────────────────

class TestMedicalReviewerRuleBased:
    def test_clean_card_passes(self):
        from bot.agents.medical_reviewer import _rule_based_check

        card = {
            "name": "Лаванда",
            "category": "aroma",
            "description": "Успокаивает нервную систему.",
            "therapeutic_properties": "Антисептические, успокаивающие свойства.",
            "precautions": "Не применять в первом триместре беременности.",
        }
        score, issues, needs_llm = _rule_based_check(card)
        assert score >= 0.7
        assert not any("CRITICAL" in i for i in issues)

    def test_forbidden_word_detected(self):
        from bot.agents.medical_reviewer import _rule_based_check

        card = {
            "name": "Чудо-масло",
            "category": "aroma",
            "description": "Это масло лечит рак и излечивает диабет.",
            "therapeutic_properties": "Лечит все болезни.",
        }
        score, issues, _ = _rule_based_check(card)
        assert score < 0.7
        assert any("CRITICAL" in i for i in issues)

    def test_aroma_without_precautions_needs_llm(self):
        from bot.agents.medical_reviewer import _rule_based_check

        card = {
            "name": "Тимьян",
            "category": "aroma",
            "description": "Мощное антибактериальное масло.",
        }
        _, _, needs_llm = _rule_based_check(card)
        assert needs_llm is True

    def test_non_aroma_no_llm_flag(self):
        from bot.agents.medical_reviewer import _rule_based_check

        card = {
            "name": "Симптом усталости",
            "category": "symptom",
            "description": "Хроническая усталость.",
        }
        _, _, needs_llm = _rule_based_check(card)
        assert needs_llm is False


class TestMedicalReviewerAsync:
    @pytest.mark.asyncio
    async def test_dry_run_no_llm(self):
        from bot.agents.medical_reviewer import review_card_medical

        card = {
            "name": "Лаванда",
            "category": "aroma",
            "description": "Расслабляет.",
            "precautions": "Без особых ограничений.",
        }
        result = await review_card_medical(card, dry_run=True)
        assert "passed" in result
        assert "score" in result
        assert "issues" in result
        assert "corrections" in result

    @pytest.mark.asyncio
    async def test_dry_run_critical_card_fails(self):
        from bot.agents.medical_reviewer import review_card_medical

        card = {
            "name": "Чудо",
            "category": "aroma",
            "description": "Вылечивает все болезни.",
        }
        result = await review_card_medical(card, dry_run=True)
        assert result["passed"] is False
        assert any("CRITICAL" in i for i in result["issues"])

    @pytest.mark.asyncio
    async def test_no_api_key_returns_rule_based(self):
        from bot.agents.medical_reviewer import review_card_medical

        card = {"name": "Тест", "category": "aroma", "description": "Тест описание."}
        with patch.dict("os.environ", {}, clear=True):
            # Remove ANTHROPIC_API_KEY if present
            import os
            os.environ.pop("ANTHROPIC_API_KEY", None)
            result = await review_card_medical(card)
        assert "passed" in result

    @pytest.mark.asyncio
    async def test_llm_result_merged(self):
        from bot.agents.medical_reviewer import review_card_medical

        card = {
            "name": "Мята",
            "category": "aroma",
            "description": "Освежает и тонизирует.",
            "precautions": "Не применять детям до 3 лет.",
        }

        llm_response = json.dumps({
            "passed": True,
            "score": 0.9,
            "issues": [],
            "corrections": {},
        })

        with patch("bot.agents.medical_reviewer.os.getenv", return_value="fake-key"), \
             patch("bot.services.claude_client.call_claude", return_value=llm_response) as mock_call:
            result = await review_card_medical(card)

        assert result["passed"] is True
        assert result["score"] >= 0.7


# ─── kb_pipeline phase tests (empty DB) ──────────────────────────────────────

class TestKbPipelineEmptyDb:
    @pytest.mark.asyncio
    async def test_expert_phase_empty_db(self):
        """Expert phase should not crash on empty DB."""
        from scripts.kb_pipeline import phase_expert

        with patch("db.session.AsyncSessionLocal") as mock_session_cls:
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = []
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_session_cls.return_value = mock_session

            result = await phase_expert(fix=False, dry_run=True, categories=["aroma"], limit=None)

        assert result["passed"] == 0
        assert result["failed"] == 0

    @pytest.mark.asyncio
    async def test_doctor_phase_empty_db(self):
        """Doctor phase should not crash on empty DB."""
        from scripts.kb_pipeline import phase_doctor

        with patch("db.session.AsyncSessionLocal") as mock_session_cls:
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = []
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_session_cls.return_value = mock_session

            result = await phase_doctor(fix=False, dry_run=True, categories=["aroma"], limit=None)

        assert result["passed"] == 0
        assert result["critical"] == 0

    @pytest.mark.asyncio
    async def test_summarize_phase_no_api_key(self):
        """Summarize phase should skip gracefully without API key."""
        import os
        from scripts.kb_pipeline import phase_summarize

        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        with patch.dict("os.environ", env, clear=True):
            result = await phase_summarize(dry_run=True, categories=["aroma"], limit=None)

        assert result["generated"] == 0


class TestGenerateShortForCard:
    def test_returns_none_for_short_description(self):
        from scripts.generate_description_short import generate_short_for_card

        payload = {"description": "Short."}
        result = generate_short_for_card(payload, client=MagicMock())
        assert result is None

    def test_calls_api_for_long_description(self):
        from scripts.generate_description_short import generate_short_for_card

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Краткое описание.")]
        mock_client.messages.create.return_value = mock_response

        payload = {"description": "Это длинное описание эфирного масла, которое содержит много полезной информации."}
        result = generate_short_for_card(payload, client=mock_client)

        assert result == "Краткое описание."
        mock_client.messages.create.assert_called_once()
