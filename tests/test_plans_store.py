"""Tests for bot/services/plans_store.py — CRUD operations on plans."""
from __future__ import annotations

import pytest

from bot.services.plans_store import (
    PlanRecord,
    get_plan,
    list_recent_plans,
    save_plan,
    update_plan_status,
)


# ---------------------------------------------------------------------------
# save_plan
# ---------------------------------------------------------------------------

class TestSavePlan:
    async def test_save_plan_returns_record(self):
        entries = [
            {"day": "Mon", "topic": "Lavender intro", "format": "instagram"},
            {"day": "Tue", "topic": "Morning blend", "format": "threads"},
        ]
        rec = await save_plan(raw_text="Week plan text", entries=entries)
        assert isinstance(rec, PlanRecord)
        assert rec.raw_text == "Week plan text"
        assert len(rec.entries) == 2
        assert rec.status == "draft"
        assert rec.plan_id  # non-empty

    async def test_save_plan_strips_raw_text(self):
        rec = await save_plan(raw_text="  padded  ", entries=[])
        assert rec.raw_text == "padded"

    async def test_save_plan_with_team_id(self):
        from bot.services.team_store import create_team

        team = await create_team("Plan Team", creator_telegram_id=222)
        rec = await save_plan(raw_text="text", entries=[], team_id=team.team_id)
        assert rec.plan_id

    async def test_save_plan_filters_invalid_entries(self):
        entries = [
            {"day": "Mon", "topic": "valid"},
            "not_a_dict",  # should be filtered
            42,  # should be filtered
            {"day": "Wed", "topic": "also_valid"},
        ]
        rec = await save_plan(raw_text="text", entries=entries)
        assert len(rec.entries) == 2

    async def test_save_plan_empty_entries(self):
        rec = await save_plan(raw_text="no entries", entries=[])
        assert rec.entries == []


# ---------------------------------------------------------------------------
# get_plan
# ---------------------------------------------------------------------------

class TestGetPlan:
    async def test_get_existing(self):
        rec = await save_plan(raw_text="text", entries=[{"a": "b"}])
        fetched = await get_plan(rec.plan_id)
        assert fetched is not None
        assert fetched.plan_id == rec.plan_id
        assert fetched.entries == [{"a": "b"}]

    async def test_get_nonexistent(self):
        result = await get_plan("nonexistent_plan_id")
        assert result is None


# ---------------------------------------------------------------------------
# list_recent_plans
# ---------------------------------------------------------------------------

class TestListRecentPlans:
    async def test_empty_list(self):
        result = await list_recent_plans()
        assert result == []

    async def test_list_with_limit(self):
        # plan_id is timestamp-based, so we save only one at a time
        # and check that limit truncates properly
        import asyncio
        for i in range(3):
            await save_plan(raw_text=f"plan_{i}", entries=[])
            await asyncio.sleep(1.1)  # ensure unique plan_id (second-based)
        result = await list_recent_plans(limit=2)
        assert len(result) == 2

    async def test_list_returns_plans(self):
        """Plans are ordered by created_at desc by default."""
        rec = await save_plan(raw_text="only_one", entries=[])
        result = await list_recent_plans()
        assert len(result) == 1
        assert result[0].raw_text == "only_one"

    async def test_filter_by_team(self):
        from bot.services.team_store import create_team

        team = await create_team("T", creator_telegram_id=1)
        await save_plan(raw_text="with_team", entries=[], team_id=team.team_id)
        # team filter includes team plans AND unassigned
        result = await list_recent_plans(team_id=team.team_id)
        assert len(result) >= 1


# ---------------------------------------------------------------------------
# update_plan_status
# ---------------------------------------------------------------------------

class TestUpdatePlanStatus:
    async def test_update_status(self):
        rec = await save_plan(raw_text="text", entries=[])
        await update_plan_status(rec.plan_id, "active")
        fetched = await get_plan(rec.plan_id)
        assert fetched.status == "active"

    async def test_update_nonexistent_is_noop(self):
        # Should not raise
        await update_plan_status("nonexistent", "active")

    async def test_status_transitions(self):
        rec = await save_plan(raw_text="text", entries=[])
        for status in ("activating", "active", "failed"):
            await update_plan_status(rec.plan_id, status)
            fetched = await get_plan(rec.plan_id)
            assert fetched.status == status


# ---------------------------------------------------------------------------
# PlanRecord edge cases
# ---------------------------------------------------------------------------

class TestPlanRecord:
    async def test_entries_default_to_empty(self):
        rec = await save_plan(raw_text="text", entries=[])
        assert rec.entries == []

    async def test_created_at_is_iso_string(self):
        rec = await save_plan(raw_text="text", entries=[])
        # Should be valid ISO datetime
        assert "T" in rec.created_at
