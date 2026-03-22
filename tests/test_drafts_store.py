"""Tests for bot/services/drafts_store.py — CRUD operations on drafts."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from bot.services.drafts_store import (
    DraftRecord,
    delete_draft,
    get_draft,
    list_recent_drafts,
    list_scheduled_drafts_due,
    save_draft,
    update_draft,
)


# ---------------------------------------------------------------------------
# save_draft
# ---------------------------------------------------------------------------

class TestSaveDraft:
    async def test_save_draft_returns_record(self):
        rec = await save_draft(
            kind="instagram",
            topic="Lavender for sleep",
            source="manual",
            payload={"caption": "test"},
        )
        assert isinstance(rec, DraftRecord)
        assert rec.kind == "instagram"
        assert rec.topic == "Lavender for sleep"
        assert rec.source == "manual"
        assert rec.status == "draft"
        assert rec.payload == {"caption": "test"}
        assert rec.draft_id  # non-empty

    async def test_save_draft_strips_whitespace(self):
        rec = await save_draft(
            kind="threads",
            topic="  spaces  ",
            source="  ai  ",
            payload={},
        )
        assert rec.topic == "spaces"
        assert rec.source == "ai"

    async def test_save_draft_with_team_and_creator(self):
        from bot.services.team_store import create_team

        team = await create_team("Test", creator_telegram_id=111)
        rec = await save_draft(
            kind="carousel",
            topic="test",
            source="ai",
            payload={},
            team_id=team.team_id,
            created_by=111,
        )
        assert rec.created_by == 111

    async def test_save_draft_unique_ids(self):
        r1 = await save_draft(kind="instagram", topic="a", source="ai", payload={})
        r2 = await save_draft(kind="instagram", topic="b", source="ai", payload={})
        assert r1.draft_id != r2.draft_id


# ---------------------------------------------------------------------------
# get_draft
# ---------------------------------------------------------------------------

class TestGetDraft:
    async def test_get_existing(self):
        rec = await save_draft(kind="threads", topic="test", source="ai", payload={"key": "val"})
        fetched = await get_draft(rec.draft_id)
        assert fetched is not None
        assert fetched.draft_id == rec.draft_id
        assert fetched.payload == {"key": "val"}

    async def test_get_nonexistent(self):
        result = await get_draft("nonexistent_id")
        assert result is None


# ---------------------------------------------------------------------------
# list_recent_drafts
# ---------------------------------------------------------------------------

class TestListRecentDrafts:
    async def test_empty_list(self):
        result = await list_recent_drafts()
        assert result == []

    async def test_list_with_limit(self):
        for i in range(5):
            await save_draft(kind="instagram", topic=f"topic_{i}", source="ai", payload={})
        result = await list_recent_drafts(limit=3)
        assert len(result) == 3

    async def test_list_newest_first(self):
        r1 = await save_draft(kind="instagram", topic="first", source="ai", payload={})
        r2 = await save_draft(kind="instagram", topic="second", source="ai", payload={})
        result = await list_recent_drafts(newest_first=True)
        assert result[0].topic == "second"
        assert result[1].topic == "first"

    async def test_filter_by_kind(self):
        await save_draft(kind="instagram", topic="ig", source="ai", payload={})
        await save_draft(kind="carousel", topic="car", source="ai", payload={})
        result = await list_recent_drafts(kind="carousel")
        assert len(result) == 1
        assert result[0].kind == "carousel"

    async def test_filter_by_status(self):
        r1 = await save_draft(kind="instagram", topic="a", source="ai", payload={})
        await update_draft(r1.draft_id, status="approved")
        await save_draft(kind="instagram", topic="b", source="ai", payload={})
        result = await list_recent_drafts(status="approved")
        assert len(result) == 1
        assert result[0].topic == "a"

    async def test_threads_filter_includes_threads_series(self):
        await save_draft(kind="threads", topic="t1", source="ai", payload={})
        await save_draft(kind="threads_series", topic="t2", source="ai", payload={})
        await save_draft(kind="instagram", topic="ig", source="ai", payload={})
        result = await list_recent_drafts(kind="threads")
        assert len(result) == 2

    async def test_filter_by_team_id(self):
        from bot.services.team_store import create_team

        team = await create_team("Team A", creator_telegram_id=1)
        await save_draft(kind="instagram", topic="team", source="ai", payload={}, team_id=team.team_id)
        await save_draft(kind="instagram", topic="no_team", source="ai", payload={})
        # Team filter includes team drafts AND unassigned (team_id=None)
        result = await list_recent_drafts(team_id=team.team_id)
        assert len(result) == 2

    async def test_filter_by_feedback(self):
        r1 = await save_draft(kind="instagram", topic="a", source="ai", payload={})
        await update_draft(r1.draft_id, feedback="approved")
        await save_draft(kind="instagram", topic="b", source="ai", payload={})
        result = await list_recent_drafts(feedback="approved")
        assert len(result) == 1


# ---------------------------------------------------------------------------
# update_draft
# ---------------------------------------------------------------------------

class TestUpdateDraft:
    async def test_update_status(self):
        rec = await save_draft(kind="instagram", topic="t", source="ai", payload={})
        updated = await update_draft(rec.draft_id, status="approved")
        assert updated.status == "approved"

    async def test_update_topic(self):
        rec = await save_draft(kind="instagram", topic="old", source="ai", payload={})
        updated = await update_draft(rec.draft_id, topic="new")
        assert updated.topic == "new"

    async def test_update_payload(self):
        rec = await save_draft(kind="instagram", topic="t", source="ai", payload={"a": 1})
        updated = await update_draft(rec.draft_id, payload={"b": 2})
        assert updated.payload == {"b": 2}

    async def test_update_scheduled_at(self):
        rec = await save_draft(kind="instagram", topic="t", source="ai", payload={})
        dt = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
        updated = await update_draft(rec.draft_id, scheduled_at=dt)
        assert updated.scheduled_at is not None

    async def test_update_scheduled_at_to_none(self):
        rec = await save_draft(kind="instagram", topic="t", source="ai", payload={})
        dt = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
        await update_draft(rec.draft_id, scheduled_at=dt)
        updated = await update_draft(rec.draft_id, scheduled_at=None)
        assert updated.scheduled_at is None

    async def test_update_publish_platforms(self):
        rec = await save_draft(kind="instagram", topic="t", source="ai", payload={})
        updated = await update_draft(rec.draft_id, publish_platforms=["threads", "instagram"])
        assert updated.publish_platforms == ["threads", "instagram"]

    async def test_update_nonexistent(self):
        result = await update_draft("nonexistent", status="approved")
        assert result is None

    async def test_update_multiple_fields(self):
        rec = await save_draft(kind="instagram", topic="t", source="ai", payload={})
        updated = await update_draft(
            rec.draft_id,
            status="published",
            feedback="approved",
            error="",
            revision_notes="Final version",
        )
        assert updated.status == "published"
        assert updated.feedback == "approved"
        assert updated.revision_notes == "Final version"

    async def test_update_external_ids(self):
        rec = await save_draft(kind="instagram", topic="t", source="ai", payload={})
        updated = await update_draft(rec.draft_id, external_ids={"threads": "123"})
        assert updated.external_ids == {"threads": "123"}

    async def test_update_team_id(self):
        from bot.services.team_store import create_team

        team = await create_team("T", creator_telegram_id=1)
        rec = await save_draft(kind="instagram", topic="t", source="ai", payload={})
        updated = await update_draft(rec.draft_id, team_id=team.team_id)
        # Verify via fresh get
        fetched = await get_draft(rec.draft_id)
        assert fetched is not None


# ---------------------------------------------------------------------------
# delete_draft
# ---------------------------------------------------------------------------

class TestDeleteDraft:
    async def test_delete_existing(self):
        rec = await save_draft(kind="instagram", topic="t", source="ai", payload={})
        result = await delete_draft(rec.draft_id)
        assert result is True
        assert await get_draft(rec.draft_id) is None

    async def test_delete_nonexistent(self):
        result = await delete_draft("nonexistent_id")
        assert result is False


# ---------------------------------------------------------------------------
# list_scheduled_drafts_due
# ---------------------------------------------------------------------------

class TestListScheduledDraftsDue:
    async def test_returns_due_drafts(self):
        rec = await save_draft(kind="instagram", topic="t", source="ai", payload={})
        past = datetime(2020, 1, 1, tzinfo=timezone.utc)
        await update_draft(rec.draft_id, status="scheduled", scheduled_at=past)
        result = await list_scheduled_drafts_due()
        assert len(result) == 1
        assert result[0].draft_id == rec.draft_id

    async def test_ignores_future_drafts(self):
        rec = await save_draft(kind="instagram", topic="t", source="ai", payload={})
        future = datetime(2099, 1, 1, tzinfo=timezone.utc)
        await update_draft(rec.draft_id, status="scheduled", scheduled_at=future)
        result = await list_scheduled_drafts_due()
        assert len(result) == 0

    async def test_ignores_non_scheduled_status(self):
        rec = await save_draft(kind="instagram", topic="t", source="ai", payload={})
        past = datetime(2020, 1, 1, tzinfo=timezone.utc)
        await update_draft(rec.draft_id, status="draft", scheduled_at=past)
        result = await list_scheduled_drafts_due()
        assert len(result) == 0


# ---------------------------------------------------------------------------
# DraftRecord.from_model edge cases
# ---------------------------------------------------------------------------

class TestDraftRecord:
    async def test_from_model_handles_none_fields(self):
        rec = await save_draft(kind="instagram", topic="t", source="ai", payload={})
        assert rec.publish_platforms == []
        assert rec.external_ids == {}
        assert rec.revision_notes == ""
        assert rec.error == ""
