"""Tests for bot.services.scheduler — asyncio loop."""

from __future__ import annotations

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
