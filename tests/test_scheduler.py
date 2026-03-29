"""Tests for bot.services.scheduler — asyncio loop."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_check_scheduled_posts_calls_publish():
    """Scheduler should call publish() for each due draft."""
    from bot.services.scheduler import _check_scheduled_posts

    mock_draft = MagicMock()
    mock_draft.draft_id = "d001"
    mock_draft.publish_platforms = ["threads", "instagram"]

    mock_app = MagicMock()

    with (
        patch(
            "bot.services.drafts_store.list_scheduled_drafts_due",
            new_callable=AsyncMock,
            return_value=[mock_draft],
        ),
        patch(
            "bot.services.publisher.publish",
            new_callable=AsyncMock,
        ) as mock_publish,
    ):
        await _check_scheduled_posts(mock_app)

    mock_publish.assert_called_once_with("d001", ["threads", "instagram"])


@pytest.mark.asyncio
async def test_check_scheduled_posts_handles_empty():
    """No drafts due — no publish calls."""
    from bot.services.scheduler import _check_scheduled_posts

    mock_app = MagicMock()

    with (
        patch(
            "bot.services.drafts_store.list_scheduled_drafts_due",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "bot.services.publisher.publish",
            new_callable=AsyncMock,
        ) as mock_publish,
    ):
        await _check_scheduled_posts(mock_app)

    mock_publish.assert_not_called()


@pytest.mark.asyncio
async def test_check_scheduled_posts_handles_publish_error():
    """If publish fails for one draft, scheduler should not crash."""
    from bot.services.scheduler import _check_scheduled_posts

    mock_draft = MagicMock()
    mock_draft.draft_id = "d002"
    mock_draft.publish_platforms = ["threads"]

    mock_app = MagicMock()

    with (
        patch(
            "bot.services.drafts_store.list_scheduled_drafts_due",
            new_callable=AsyncMock,
            return_value=[mock_draft],
        ),
        patch(
            "bot.services.publisher.publish",
            new_callable=AsyncMock,
            side_effect=RuntimeError("API down"),
        ),
    ):
        # Should not raise
        await _check_scheduled_posts(mock_app)


def test_is_digest_time():
    from bot.services.scheduler import _is_digest_time

    with patch("bot.services.scheduler.settings") as mock_settings:
        mock_settings.digest_hour = 9
        mock_settings.digest_minute = 0

        now_match = datetime(2026, 3, 15, 9, 0, tzinfo=timezone.utc)
        now_no_match = datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc)

        assert _is_digest_time(now_match) is True
        assert _is_digest_time(now_no_match) is False


def test_comments_poll_hours_config():
    """Comments polling should be configured for every 3 hours at :30."""
    from bot.services.scheduler import _COMMENTS_POLL_HOURS, _COMMENTS_POLL_MINUTE

    assert _COMMENTS_POLL_HOURS == {0, 3, 6, 9, 12, 15, 18, 21}
    assert _COMMENTS_POLL_MINUTE == 30


@pytest.mark.asyncio
async def test_run_loop_triggers_comments_poll():
    """run_loop should call poll_published_comments at the right time."""
    import bot.services.scheduler as sched_mod

    call_count = 0
    mock_app = MagicMock()

    async def fake_poll(team_id=None):
        nonlocal call_count
        call_count += 1
        return (10, 3)  # total_polled, newly_saved

    # Simulate loop: first sleep returns, then second sleep cancels
    sleep_calls = 0

    async def fake_sleep(seconds):
        nonlocal sleep_calls
        sleep_calls += 1
        if sleep_calls > 1:
            raise asyncio.CancelledError()

    # Time: 09:30 UTC — should trigger comments poll
    fake_now = datetime(2026, 3, 15, 9, 30, tzinfo=timezone.utc)

    with (
        patch.object(sched_mod.asyncio, "sleep", side_effect=fake_sleep),
        patch.object(sched_mod, "datetime") as mock_dt,
        patch("bot.services.comments_poller.poll_published_comments", side_effect=fake_poll),
        patch.object(sched_mod, "_check_scheduled_posts", new_callable=AsyncMock),
        patch.object(sched_mod, "settings") as mock_settings,
    ):
        mock_dt.now.return_value = fake_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        mock_settings.digest_hour = 99  # disable digest
        mock_settings.digest_minute = 99
        mock_settings.daily_digest_time = "99:99"
        mock_settings.timezone = "UTC"

        with pytest.raises(asyncio.CancelledError):
            await sched_mod.run_loop(mock_app)

    assert call_count == 1, f"Expected poll_published_comments called once, got {call_count}"


@pytest.mark.asyncio
async def test_run_loop_comments_poll_error_does_not_block():
    """If comments polling fails, other scheduler tasks should continue."""
    import bot.services.scheduler as sched_mod

    sleep_calls = 0

    async def fake_sleep(seconds):
        nonlocal sleep_calls
        sleep_calls += 1
        if sleep_calls > 1:
            raise asyncio.CancelledError()

    fake_now = datetime(2026, 3, 15, 9, 30, tzinfo=timezone.utc)

    mock_app = MagicMock()
    scheduled_posts_called = False

    async def track_scheduled_posts(app):
        nonlocal scheduled_posts_called
        scheduled_posts_called = True

    with (
        patch.object(sched_mod.asyncio, "sleep", side_effect=fake_sleep),
        patch.object(sched_mod, "datetime") as mock_dt,
        patch(
            "bot.services.comments_poller.poll_published_comments",
            new_callable=AsyncMock,
            side_effect=RuntimeError("API unavailable"),
        ),
        patch.object(sched_mod, "_check_scheduled_posts", side_effect=track_scheduled_posts),
        patch.object(sched_mod, "settings") as mock_settings,
    ):
        mock_dt.now.return_value = fake_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        mock_settings.digest_hour = 99
        mock_settings.digest_minute = 99
        mock_settings.daily_digest_time = "99:99"
        mock_settings.timezone = "UTC"

        with pytest.raises(asyncio.CancelledError):
            await sched_mod.run_loop(mock_app)

    # Scheduled posts check should still have run despite comments poll failure
    assert scheduled_posts_called, "Scheduled posts check should run even if comments poll fails"


# ---------------------------------------------------------------------------
# Tests for the declarative ScheduledTask registry
# ---------------------------------------------------------------------------


def test_scheduled_task_daily():
    """ScheduledTask with check='daily' should fire once per day."""
    from bot.services.scheduler import ScheduledTask

    task = ScheduledTask(
        name="test_daily",
        fn=AsyncMock(),
        hours={9},
        minute=0,
        check="daily",
    )

    now_match = datetime(2026, 3, 15, 9, 0, tzinfo=timezone.utc)
    now_wrong_hour = datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc)
    now_wrong_minute = datetime(2026, 3, 15, 9, 5, tzinfo=timezone.utc)

    assert task.should_run(now_wrong_hour) is False
    assert task.should_run(now_wrong_minute) is False
    assert task.should_run(now_match) is True
    # Second call same day should not fire
    assert task.should_run(now_match) is False
    # Next day should fire
    next_day = datetime(2026, 3, 16, 9, 0, tzinfo=timezone.utc)
    assert task.should_run(next_day) is True


def test_scheduled_task_hourly():
    """ScheduledTask with check='hourly' should fire once per matching hour."""
    from bot.services.scheduler import ScheduledTask

    task = ScheduledTask(
        name="test_hourly",
        fn=AsyncMock(),
        hours={0, 6, 12, 18},
        minute=0,
        check="hourly",
    )

    assert task.should_run(datetime(2026, 3, 15, 6, 0, tzinfo=timezone.utc)) is True
    assert task.should_run(datetime(2026, 3, 15, 6, 0, tzinfo=timezone.utc)) is False  # dedup
    assert task.should_run(datetime(2026, 3, 15, 7, 0, tzinfo=timezone.utc)) is False  # wrong hour
    assert task.should_run(datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc)) is True


def test_scheduled_task_every_nm():
    """ScheduledTask with check='every_Nm' fires on interval minutes."""
    from bot.services.scheduler import ScheduledTask

    task = ScheduledTask(
        name="test_every5m",
        fn=AsyncMock(),
        check="every_Nm",
        interval_minutes=5,
    )

    assert task.should_run(datetime(2026, 3, 15, 9, 0, tzinfo=timezone.utc)) is True
    assert task.should_run(datetime(2026, 3, 15, 9, 0, tzinfo=timezone.utc)) is False  # dedup
    assert task.should_run(datetime(2026, 3, 15, 9, 3, tzinfo=timezone.utc)) is False  # not on interval
    assert task.should_run(datetime(2026, 3, 15, 9, 5, tzinfo=timezone.utc)) is True


def test_scheduled_task_every_tick():
    """ScheduledTask with check='every_tick' fires every time."""
    from bot.services.scheduler import ScheduledTask

    task = ScheduledTask(
        name="test_tick",
        fn=AsyncMock(),
        check="every_tick",
    )

    assert task.should_run(datetime(2026, 3, 15, 9, 0, tzinfo=timezone.utc)) is True
    assert task.should_run(datetime(2026, 3, 15, 9, 1, tzinfo=timezone.utc)) is True


def test_build_task_registry():
    """Registry should contain all expected tasks."""
    from bot.services.scheduler import _build_task_registry

    registry = _build_task_registry()
    names = {t.name for t in registry}

    expected = {
        "daily_digest", "cost_report", "daily_oil", "token_expiry_check",
        "post_metrics", "thread_monitor", "social_trends_pipeline",
        "comments_poll", "mentions_poll", "status_monitor", "scheduled_posts",
    }
    assert expected == names
