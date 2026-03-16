"""Tests for plan activation service."""
from __future__ import annotations

import pytest
from datetime import datetime, timezone

from bot.services.plans_store import save_plan, get_plan, update_plan_status
from bot.services.drafts_store import get_draft
from bot.services.plan_activation import activate_plan, _resolve_scheduled_at


@pytest.mark.asyncio
async def test_activate_plan_creates_drafts(setup_test_db, monkeypatch):
    import bot.services.plan_activation
    import bot.services.plans_store as ps_mod
    import bot.services.drafts_store as ds_mod

    monkeypatch.setattr(bot.services.plan_activation, "get_plan", ps_mod.get_plan)
    monkeypatch.setattr(bot.services.plan_activation, "update_plan_status", ps_mod.update_plan_status)
    monkeypatch.setattr(bot.services.plan_activation, "save_draft", ds_mod.save_draft)
    monkeypatch.setattr(bot.services.plan_activation, "update_draft", ds_mod.update_draft)

    plan = await save_plan(
        raw_text="Test plan",
        entries=[
            {"day_label": "\u041f\u043d", "platform": "Threads", "format_label": "\u041f\u043e\u0441\u0442", "topic": "Topic A", "angle": "", "goal": ""},
            {"day_label": "\u0421\u0440", "platform": "Instagram", "format_label": "\u0420\u0438\u043b\u0441", "topic": "Topic B", "angle": "", "goal": ""},
            {"day_label": "\u041f\u0442", "platform": "Telegram", "format_label": "\u041f\u043e\u0441\u0442", "topic": "Topic C", "angle": "", "goal": ""},
        ],
    )

    now = datetime(2026, 3, 16, 12, 0, tzinfo=timezone.utc)
    result = await activate_plan(plan.plan_id, now=now)

    assert result["plan_id"] == plan.plan_id
    assert result["activated_count"] == 3
    assert len(result["drafts"]) == 3

    for d in result["drafts"]:
        draft = await get_draft(d["draft_id"])
        assert draft is not None
        assert draft.status == "scheduled"
        assert draft.scheduled_at is not None
        assert len(draft.publish_platforms) > 0

    updated_plan = await get_plan(plan.plan_id)
    assert updated_plan.status == "active"


@pytest.mark.asyncio
async def test_activate_plan_skips_empty_topics(setup_test_db, monkeypatch):
    import bot.services.plan_activation
    import bot.services.plans_store as ps_mod
    import bot.services.drafts_store as ds_mod

    monkeypatch.setattr(bot.services.plan_activation, "get_plan", ps_mod.get_plan)
    monkeypatch.setattr(bot.services.plan_activation, "update_plan_status", ps_mod.update_plan_status)
    monkeypatch.setattr(bot.services.plan_activation, "save_draft", ds_mod.save_draft)
    monkeypatch.setattr(bot.services.plan_activation, "update_draft", ds_mod.update_draft)

    plan = await save_plan(
        raw_text="Plan with empty",
        entries=[
            {"day_label": "\u041f\u043d", "platform": "Threads", "format_label": "\u041f\u043e\u0441\u0442", "topic": "", "angle": "", "goal": ""},
            {"day_label": "\u0412\u0442", "platform": "Threads", "format_label": "\u041f\u043e\u0441\u0442", "topic": "Real topic", "angle": "", "goal": ""},
        ],
    )

    result = await activate_plan(plan.plan_id)
    assert result["activated_count"] == 1


def test_resolve_scheduled_at_monday():
    now = datetime(2026, 3, 18, 12, 0, tzinfo=timezone.utc)
    result = _resolve_scheduled_at("\u041f\u043d", "threads", now=now)
    assert result.weekday() == 0
    assert result.hour == 7
    assert result > now


def test_resolve_scheduled_at_same_day_past():
    now = datetime(2026, 3, 16, 8, 0, tzinfo=timezone.utc)
    result = _resolve_scheduled_at("\u041f\u043d", "threads", now=now)
    assert result.weekday() == 0
    assert result > now
    assert result.day == 23


@pytest.mark.asyncio
async def test_update_plan_status(setup_test_db):
    plan = await save_plan(raw_text="Status test", entries=[])
    assert plan.status == "draft"

    await update_plan_status(plan.plan_id, "active")
    updated = await get_plan(plan.plan_id)
    assert updated.status == "active"
