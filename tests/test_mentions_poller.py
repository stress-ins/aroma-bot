"""Tests for bot.services.mentions_poller."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture()
def _mock_threads_client():
    """Patch ThreadsClient to return controllable data."""
    client = MagicMock()
    client.get_mentions.return_value = [
        {"id": "t_1", "username": "alice", "text": "Hello!", "media_type": "TEXT", "permalink": "https://threads.net/1"},
    ]
    client.get_threads.return_value = [
        {"id": "t_2", "username": "bob", "text": "Nice post", "media_type": "TEXT", "permalink": "https://threads.net/2"},
    ]
    client.get_replies.return_value = [
        {"id": "r_1", "username": "carol", "text": "Reply!", "permalink": "https://threads.net/r1"},
    ]
    with patch("bot.services.mentions_poller.ThreadsClient", return_value=client) as mock_cls:
        mock_cls._instance = client
        yield client


@pytest.fixture()
def _mock_store():
    """Patch mentions_store functions."""
    with (
        patch("bot.services.mentions_poller.find_mention_by_external_id", new_callable=AsyncMock) as mock_find,
        patch("bot.services.mentions_poller.save_mention", new_callable=AsyncMock) as mock_save,
    ):
        mock_find.return_value = None  # nothing exists by default
        mock_save.return_value = ("mid_123", True)
        yield {"find": mock_find, "save": mock_save}


@pytest.mark.asyncio
async def test_poll_saves_new(_mock_threads_client, _mock_store):
    from bot.services.mentions_poller import poll_threads_mentions

    polled, saved = await poll_threads_mentions("fake_token")
    # 1 mention from get_mentions (get_threads no longer called) + 1 reply = 2 saves
    assert polled == 1
    assert saved == 2
    assert _mock_store["save"].call_count == 2


@pytest.mark.asyncio
async def test_poll_deduplicates(_mock_threads_client, _mock_store):
    from bot.services.mentions_poller import poll_threads_mentions

    # All items already exist
    existing = MagicMock()
    _mock_store["find"].return_value = existing

    polled, saved = await poll_threads_mentions("fake_token")
    assert polled == 1
    assert saved == 0
    assert _mock_store["save"].call_count == 0


@pytest.mark.asyncio
async def test_poll_handles_api_error(_mock_store):
    """API errors don't crash — just log warnings and return 0."""
    client = MagicMock()
    client.get_mentions.side_effect = Exception("API down")
    client.get_threads.side_effect = Exception("API down")

    with patch("bot.services.mentions_poller.ThreadsClient", return_value=client):
        from bot.services.mentions_poller import poll_threads_mentions

        polled, saved = await poll_threads_mentions("fake_token")
        assert polled == 0
        assert saved == 0


@pytest.mark.asyncio
async def test_poll_all_teams_iterates():
    """poll_all_teams iterates configured teams."""
    team_data = [{"team_id": "team_a", "has_ig": False, "has_threads": True}]
    token_row = MagicMock()
    token_row.access_token = "token_a"

    with (
        patch("bot.services.mentions_poller.list_teams_with_social_accounts", new_callable=AsyncMock, return_value=team_data),
        patch("bot.services.mentions_poller.get_token_for_team", new_callable=AsyncMock, return_value=token_row),
        patch("bot.services.mentions_poller.poll_threads_mentions", new_callable=AsyncMock, return_value=(5, 2)) as mock_poll,
        patch("bot.services.mentions_poller.get_token", new_callable=AsyncMock),
    ):
        from bot.services.mentions_poller import poll_all_teams

        results = await poll_all_teams()
        assert "team_a" in results
        assert results["team_a"] == (5, 2)
        mock_poll.assert_called_once_with("token_a", "team_a")


@pytest.mark.asyncio
async def test_global_token_fallback():
    """Falls back to global token when no teams configured."""
    token_row = MagicMock()
    token_row.access_token = "global_token"

    with (
        patch("bot.services.mentions_poller.list_teams_with_social_accounts", new_callable=AsyncMock, return_value=[]),
        patch("bot.services.mentions_poller.get_token", new_callable=AsyncMock, return_value=token_row),
        patch("bot.services.mentions_poller.poll_threads_mentions", new_callable=AsyncMock, return_value=(3, 1)) as mock_poll,
    ):
        from bot.services.mentions_poller import poll_all_teams

        results = await poll_all_teams()
        assert "global" in results
        assert results["global"] == (3, 1)
        mock_poll.assert_called_once_with("global_token")
