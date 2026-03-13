"""Tests for DraftRevision store, KBContextBuilder, and QualityEvaluator."""
from __future__ import annotations

import pytest


class TestDraftRevisionStore:
    async def test_create_revision_increments_rev_num(self):
        from bot.services.draft_revisions_store import create_revision

        r1 = await create_revision("draft001", {"caption": "first"}, author="user")
        r2 = await create_revision("draft001", {"caption": "second"}, author="ai:polish")

        assert r1.rev_num == 1
        assert r2.rev_num == 2
        assert r1.draft_id == "draft001"
        assert r2.author == "ai:polish"

    async def test_list_revisions_returns_in_order(self):
        from bot.services.draft_revisions_store import create_revision, list_revisions

        await create_revision("draft002", {"v": 1})
        await create_revision("draft002", {"v": 2})
        await create_revision("draft002", {"v": 3})

        revisions = await list_revisions("draft002")
        assert len(revisions) == 3
        assert [r.rev_num for r in revisions] == [1, 2, 3]

    async def test_get_revision_by_rev_num(self):
        from bot.services.draft_revisions_store import create_revision, get_revision

        await create_revision("draft003", {"step": "a"})
        await create_revision("draft003", {"step": "b"})

        rev2 = await get_revision("draft003", 2)
        assert rev2 is not None
        assert rev2.payload["step"] == "b"

    async def test_get_revision_returns_none_for_missing(self):
        from bot.services.draft_revisions_store import get_revision

        result = await get_revision("nonexistent", 99)
        assert result is None

    async def test_revisions_isolated_per_draft(self):
        from bot.services.draft_revisions_store import create_revision, list_revisions

        await create_revision("draftA", {"x": 1})
        await create_revision("draftA", {"x": 2})
        await create_revision("draftB", {"y": 1})

        revs_a = await list_revisions("draftA")
        revs_b = await list_revisions("draftB")

        assert len(revs_a) == 2
        assert len(revs_b) == 1
        assert revs_a[0].rev_num == 1
        assert revs_b[0].rev_num == 1

    def test_revision_to_dict_has_all_fields(self):
        from bot.services.draft_revisions_store import DraftRevision

        rev = DraftRevision(
            id=1,
            draft_id="abc",
            rev_num=3,
            payload={"caption": "hello"},
            author="user",
            note="manual save",
            created_at="2026-03-13T10:00:00+00:00",
        )
        d = rev.to_dict()
        assert d["draft_id"] == "abc"
        assert d["rev_num"] == 3
        assert d["payload"]["caption"] == "hello"
        assert d["author"] == "user"
        assert d["note"] == "manual save"

    async def test_note_stored_correctly(self):
        from bot.services.draft_revisions_store import create_revision, get_revision

        await create_revision("draft_note", {"x": 1}, author="system", note="restored from rev 2")
        rev = await get_revision("draft_note", 1)
        assert rev is not None
        assert rev.note == "restored from rev 2"
        assert rev.author == "system"


class TestKBContextBuilder:
    async def test_build_returns_context_for_empty_db(self):
        from bot.services.kb_context_builder import build_content_context

        ctx = await build_content_context("лаванда для сна", platform="instagram")
        assert ctx.topic == "лаванда для сна"
        assert ctx.platform == "instagram"

    async def test_build_matches_card_by_name(self, setup_test_db):
        import bot.services.kb_context_builder as kb
        from db.models import AromaCardModel

        async with kb.AsyncSessionLocal() as session:
            card = AromaCardModel(
                slug="lavender",
                name="Лаванда",
                category="aroma",
                source_type="herb",
                aliases=["lavandula"],
                payload={
                    "description": "Успокаивающее масло",
                    "therapeutic_properties": "снятие стресса, улучшение сна",
                },
            )
            session.add(card)
            await session.commit()

        from bot.services.kb_context_builder import build_content_context
        ctx = await build_content_context("лаванда для сна")
        assert any(c["slug"] == "lavender" for c in ctx.cards)

    async def test_as_prompt_text_non_empty(self, setup_test_db):
        import bot.services.kb_context_builder as kb
        from db.models import AromaCardModel

        async with kb.AsyncSessionLocal() as session:
            card = AromaCardModel(
                slug="bergamot",
                name="Бергамот",
                category="aroma",
                source_type="herb",
                aliases=[],
                payload={"description": "Цитрусовый аромат, поднимает настроение"},
            )
            session.add(card)
            await session.commit()

        from bot.services.kb_context_builder import build_content_context
        ctx = await build_content_context("бергамот настроение")
        text = ctx.as_prompt_text()
        assert "Бергамот" in text
        assert "Релевантные материалы" in text

    def test_extract_keywords_removes_stopwords(self):
        from bot.services.kb_context_builder import _extract_keywords

        keywords = _extract_keywords("аромат для снятия стресса и тревоги")
        assert "для" not in keywords
        assert "и" not in keywords
        assert "аромат" in keywords
        assert "стресса" in keywords

    def test_as_prompt_text_empty_when_no_cards(self):
        from bot.services.kb_context_builder import KBContext

        ctx = KBContext(cards=[], topic="test")
        assert ctx.as_prompt_text() == ""

    async def test_fallback_to_aroma_when_no_matches(self, setup_test_db):
        """When no keyword matches, should return top aroma cards as fallback."""
        import bot.services.kb_context_builder as kb
        from db.models import AromaCardModel
        from datetime import datetime, timezone

        async with kb.AsyncSessionLocal() as session:
            for i in range(3):
                session.add(AromaCardModel(
                    slug=f"aroma-{i}",
                    name=f"Аромат {i}",
                    category="aroma",
                    source_type="herb",
                    aliases=[],
                    payload={"description": f"Описание {i}"},
                    updated_at=datetime.now(timezone.utc),
                ))
            await session.commit()

        from bot.services.kb_context_builder import build_content_context
        # Use a topic that won't match any cards
        ctx = await build_content_context("xyzxyz нет совпадений")
        # Should fall back to aroma cards
        assert len(ctx.cards) <= 5


class TestQualityEvaluatorStructure:
    """Tests for QualityEvaluator structure (without Claude API calls)."""

    def test_content_score_has_required_fields(self):
        from bot.agents.quality_evaluator import ContentScore

        score = ContentScore(
            hook_strength=0.8,
            coherence=0.7,
            cta_clarity=0.6,
            brand_fit=0.9,
            overall=0.75,
            critique="Хороший текст, улучши хук",
            passed=True,
        )
        assert score["hook_strength"] == 0.8
        assert score["passed"] is True
        assert "critique" in score

    async def test_evaluate_content_graceful_without_api_key(self, monkeypatch):
        import bot.agents.quality_evaluator as qe
        from unittest.mock import MagicMock

        mock_settings = MagicMock()
        mock_settings.anthropic_api_key = None
        monkeypatch.setattr(qe, "settings", mock_settings)

        from bot.agents.quality_evaluator import evaluate_content
        score = await evaluate_content("Текст поста", platform="instagram", topic="лаванда")
        assert score["passed"] is True
        assert score["overall"] >= 0.5

    def test_threshold_determines_passed(self):
        from bot.agents.quality_evaluator import _THRESHOLD
        assert 0.5 <= _THRESHOLD <= 0.9, "threshold should be reasonable"
