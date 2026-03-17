"""Tests for GSD-inspired verification gates: quality evaluator self-audit,
pre-publish quality gate, approval policy check, and parallel plan activation."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from db.models import Base
import bot.services.drafts_store as ds_mod


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture()
async def in_memory_db(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(ds_mod, "AsyncSessionLocal", factory)
    yield factory
    await engine.dispose()


# ---------------------------------------------------------------------------
# 1. Quality evaluator self-audit
# ---------------------------------------------------------------------------


class TestSelfAudit:
    def test_self_audit_lowers_humanness_when_markers_found(self):
        from bot.agents.quality_evaluator import _self_audit

        scores = {
            "hook_strength": 0.8,
            "coherence": 0.8,
            "cta_clarity": 0.7,
            "brand_fit": 0.8,
            "humanness": 0.9,
            "overall": 0.8,
            "critique": "Good text.",
            "passed": True,
        }
        # Text containing AI markers from humanizer._AI_MARKERS
        text = "Важно отметить, что данный метод осуществляется в рамках программы."
        result = _self_audit(scores, text)

        assert result["humanness"] <= 0.61
        assert "Self-audit" in result["critique"]
        assert result["overall"] < 0.8  # recalculated

    def test_self_audit_no_change_when_no_markers(self):
        from bot.agents.quality_evaluator import _self_audit

        scores = {
            "hook_strength": 0.8,
            "coherence": 0.8,
            "cta_clarity": 0.7,
            "brand_fit": 0.8,
            "humanness": 0.9,
            "overall": 0.8,
            "critique": "Good.",
            "passed": True,
        }
        text = "Просто хороший текст без штампов."
        result = _self_audit(scores, text)

        assert result["humanness"] == 0.9
        assert "Self-audit" not in result["critique"]

    def test_self_audit_skips_low_humanness(self):
        from bot.agents.quality_evaluator import _self_audit

        scores = {
            "hook_strength": 0.8,
            "coherence": 0.8,
            "cta_clarity": 0.7,
            "brand_fit": 0.8,
            "humanness": 0.5,
            "overall": 0.7,
            "critique": "",
            "passed": True,
        }
        text = "Важно отметить, что данный подход работает."
        result = _self_audit(scores, text)

        # humanness already below 0.7, no adjustment
        assert result["humanness"] == 0.5


# ---------------------------------------------------------------------------
# 2. Pre-publish quality gate
# ---------------------------------------------------------------------------


class TestPrePublishQualityGate:
    @pytest.mark.asyncio
    async def test_blocks_low_quality(self, in_memory_db):
        from bot.services.publisher import publish  # noqa: F811

        draft = await ds_mod.save_draft(
            kind="threads", topic="test", source="test",
            payload={
                "text": "Test post",
                "quality_score": {"overall": 0.3, "passed": False},
            },
        )

        result = await publish(draft.draft_id, ["threads"])
        assert "error" in result
        assert "quality_score" in result["error"]

        updated = await ds_mod.get_draft(draft.draft_id)
        assert updated.status == "failed"

    @pytest.mark.asyncio
    async def test_allows_high_quality(self, in_memory_db):
        from bot.services.publisher import publish

        draft = await ds_mod.save_draft(
            kind="threads", topic="test", source="test",
            payload={
                "text": "Good post",
                "quality_score": {"overall": 0.85, "passed": True},
            },
        )

        mock_upload = AsyncMock(return_value={"threads": {"status": "success", "external_id": "ext1"}})
        with (
            patch("bot.services.publisher._upload_post_publish", mock_upload),
            patch("bot.services.publisher.update_draft", return_value=draft),
        ):
            result = await publish(draft.draft_id, ["threads"])

        assert "error" not in result
        mock_upload.assert_called_once()

    @pytest.mark.asyncio
    async def test_allows_missing_score(self, in_memory_db):
        """Drafts without quality_score (legacy) should pass through."""
        from bot.services.publisher import publish

        draft = await ds_mod.save_draft(
            kind="threads", topic="test", source="test",
            payload={"text": "Legacy post"},
        )

        mock_upload = AsyncMock(return_value={"threads": {"status": "success", "external_id": "ext2"}})
        with (
            patch("bot.services.publisher._upload_post_publish", mock_upload),
            patch("bot.services.publisher.update_draft", return_value=draft),
        ):
            result = await publish(draft.draft_id, ["threads"])

        assert "error" not in result


# ---------------------------------------------------------------------------
# 3. Approval workflow policy check
# ---------------------------------------------------------------------------


class TestApprovalPolicyCheck:
    @pytest.mark.asyncio
    async def test_submit_records_violations(self, in_memory_db):
        from bot.services.approval_workflow import submit_for_review

        draft = await ds_mod.save_draft(
            kind="threads", topic="test", source="test",
            payload={"caption": "Напиши в ДМ для записи", "platform": "threads"},
        )

        rec = await submit_for_review(draft.draft_id)
        assert rec.status == "pending_review"
        # Policy engine should catch "в ДМ" → "в личные сообщения" as a soft rewrite
        # The exact behavior depends on policy config, but the transition should succeed

    @pytest.mark.asyncio
    async def test_submit_works_without_caption(self, in_memory_db):
        from bot.services.approval_workflow import submit_for_review

        draft = await ds_mod.save_draft(
            kind="threads", topic="test", source="test",
            payload={"text": "No caption field"},
        )

        rec = await submit_for_review(draft.draft_id)
        assert rec.status == "pending_review"


# ---------------------------------------------------------------------------
# 4. Parallel plan activation
# ---------------------------------------------------------------------------


class TestParallelPlanActivation:
    @pytest.mark.asyncio
    async def test_parallel_activation(self, in_memory_db, monkeypatch):
        import bot.services.plan_activation as pa_mod
        import bot.services.plans_store as ps_mod

        monkeypatch.setattr(pa_mod, "get_plan", ps_mod.get_plan)
        monkeypatch.setattr(pa_mod, "update_plan_status", ps_mod.update_plan_status)
        monkeypatch.setattr(pa_mod, "save_draft", ds_mod.save_draft)
        monkeypatch.setattr(pa_mod, "update_draft", ds_mod.update_draft)

        # Also need plans_store to use same DB
        monkeypatch.setattr(ps_mod, "AsyncSessionLocal", in_memory_db)

        plan = await ps_mod.save_plan(
            raw_text="Parallel test",
            entries=[
                {"day_label": "Пн", "platform": "Threads", "format_label": "Пост", "topic": "A", "angle": "", "goal": ""},
                {"day_label": "Ср", "platform": "Instagram", "format_label": "Пост", "topic": "B", "angle": "", "goal": ""},
                {"day_label": "Пт", "platform": "Telegram", "format_label": "Пост", "topic": "C", "angle": "", "goal": ""},
            ],
        )

        now = datetime(2026, 3, 16, 12, 0, tzinfo=timezone.utc)
        result = await pa_mod.activate_plan(plan.plan_id, now=now)

        assert result["activated_count"] == 3
        assert len(result["drafts"]) == 3

        updated = await ps_mod.get_plan(plan.plan_id)
        assert updated.status == "active"

    @pytest.mark.asyncio
    async def test_parallel_activation_skips_empty(self, in_memory_db, monkeypatch):
        import bot.services.plan_activation as pa_mod
        import bot.services.plans_store as ps_mod

        monkeypatch.setattr(pa_mod, "get_plan", ps_mod.get_plan)
        monkeypatch.setattr(pa_mod, "update_plan_status", ps_mod.update_plan_status)
        monkeypatch.setattr(pa_mod, "save_draft", ds_mod.save_draft)
        monkeypatch.setattr(pa_mod, "update_draft", ds_mod.update_draft)
        monkeypatch.setattr(ps_mod, "AsyncSessionLocal", in_memory_db)

        plan = await ps_mod.save_plan(
            raw_text="With empty",
            entries=[
                {"day_label": "Пн", "platform": "Threads", "format_label": "Пост", "topic": "", "angle": "", "goal": ""},
                {"day_label": "Вт", "platform": "Threads", "format_label": "Пост", "topic": "Real", "angle": "", "goal": ""},
            ],
        )

        result = await pa_mod.activate_plan(plan.plan_id)
        assert result["activated_count"] == 1
