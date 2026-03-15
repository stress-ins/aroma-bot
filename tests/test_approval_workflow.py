"""Tests for bot.services.approval_workflow — status transitions."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from db.models import Base, DraftModel
import bot.services.drafts_store as ds_mod
from bot.services.approval_workflow import (
    submit_for_review,
    approve,
    request_revision,
    schedule,
    mark_published,
    mark_failed,
    InvalidTransitionError,
)


@pytest_asyncio.fixture()
async def in_memory_db(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(ds_mod, "AsyncSessionLocal", factory)
    yield factory
    await engine.dispose()


async def _seed_draft(status: str = "draft") -> str:
    rec = await ds_mod.save_draft(
        kind="threads", topic="test", source="test", payload={"text": "hello"}
    )
    if status != "draft":
        await ds_mod.update_draft(rec.draft_id, status=status)
    return rec.draft_id


# ------------------------------------------------------------------
# Happy-path transitions
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_submit_for_review(in_memory_db):
    did = await _seed_draft("draft")
    rec = await submit_for_review(did)
    assert rec.status == "pending_review"


@pytest.mark.asyncio
async def test_approve(in_memory_db):
    did = await _seed_draft("pending_review")
    rec = await approve(did)
    assert rec.status == "approved"


@pytest.mark.asyncio
async def test_request_revision(in_memory_db):
    did = await _seed_draft("pending_review")
    rec = await request_revision(did, "fix the intro")
    assert rec.status == "revision_requested"
    assert rec.revision_notes == "fix the intro"


@pytest.mark.asyncio
async def test_revision_requested_back_to_draft(in_memory_db):
    """revision_requested can only go back to draft (not directly to pending_review)."""
    did = await _seed_draft("revision_requested")
    # revision_requested → draft
    rec = await ds_mod.update_draft(did, status="draft")
    assert rec.status == "draft"
    # Now draft → pending_review works
    rec = await submit_for_review(did)
    assert rec.status == "pending_review"


@pytest.mark.asyncio
async def test_revision_requested_to_draft(in_memory_db):
    did = await _seed_draft("pending_review")
    await request_revision(did, "fix intro")
    # Now it's revision_requested, transition back to draft
    draft = await ds_mod.get_draft(did)
    assert draft.status == "revision_requested"
    # revision_requested → draft
    await ds_mod.update_draft(did, status="draft")
    rec = await submit_for_review(did)
    assert rec.status == "pending_review"


@pytest.mark.asyncio
async def test_schedule(in_memory_db):
    did = await _seed_draft("approved")
    dt = datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc)
    rec = await schedule(did, dt, ["threads", "instagram"])
    assert rec.status == "scheduled"
    assert rec.publish_platforms == ["threads", "instagram"]


@pytest.mark.asyncio
async def test_mark_published(in_memory_db):
    did = await _seed_draft("scheduled")
    rec = await mark_published(did, {"threads": "ext123"})
    assert rec.status == "published"
    assert rec.published_at is not None
    assert rec.external_ids == {"threads": "ext123"}


@pytest.mark.asyncio
async def test_mark_failed_from_scheduled(in_memory_db):
    did = await _seed_draft("scheduled")
    rec = await mark_failed(did, "upload-post timeout")
    assert rec.status == "failed"
    assert rec.error == "upload-post timeout"


@pytest.mark.asyncio
async def test_mark_failed_from_published(in_memory_db):
    did = await _seed_draft("published")
    rec = await mark_failed(did, "post removed")
    assert rec.status == "failed"
    assert rec.error == "post removed"


# ------------------------------------------------------------------
# Full happy path
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_lifecycle(in_memory_db):
    did = await _seed_draft("draft")
    await submit_for_review(did)
    await approve(did)
    await schedule(did, datetime(2026, 4, 1, tzinfo=timezone.utc), ["threads"])
    rec = await mark_published(did, {"threads": "abc"})
    assert rec.status == "published"


# ------------------------------------------------------------------
# Invalid transitions
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cannot_approve_draft(in_memory_db):
    did = await _seed_draft("draft")
    with pytest.raises(InvalidTransitionError):
        await approve(did)


@pytest.mark.asyncio
async def test_cannot_schedule_draft(in_memory_db):
    did = await _seed_draft("draft")
    with pytest.raises(InvalidTransitionError):
        await schedule(did, datetime.now(timezone.utc), ["threads"])


@pytest.mark.asyncio
async def test_cannot_publish_approved(in_memory_db):
    did = await _seed_draft("approved")
    with pytest.raises(InvalidTransitionError):
        await mark_published(did, {})


@pytest.mark.asyncio
async def test_cannot_schedule_pending_review(in_memory_db):
    did = await _seed_draft("pending_review")
    with pytest.raises(InvalidTransitionError):
        await schedule(did, datetime.now(timezone.utc), ["threads"])


@pytest.mark.asyncio
async def test_cannot_fail_draft(in_memory_db):
    did = await _seed_draft("draft")
    with pytest.raises(InvalidTransitionError):
        await mark_failed(did, "err")


@pytest.mark.asyncio
async def test_draft_not_found_raises(in_memory_db):
    with pytest.raises(ValueError, match="not found"):
        await submit_for_review("nonexistent")
