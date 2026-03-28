"""Tests for auto-refresh of all platform tokens in check_expiring_tokens()."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_token(platform: str, *, days_left: int = 3, refresh_token: str = "rt"):
    expires_at = datetime.now(timezone.utc) + timedelta(days=days_left)
    return SimpleNamespace(
        platform=platform,
        access_token=f"{platform}_access_tok",
        refresh_token=refresh_token,
        expires_at=expires_at,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("platform", ["threads", "instagram", "facebook", "canva", "youtube", "tiktok"])
async def test_check_expiring_tokens_auto_refreshes_all_platforms(platform, setup_test_db):
    """check_expiring_tokens() auto-refreshes tokens for all supported platforms."""
    token = _make_token(platform)

    with (
        patch("bot.services.mentions_poller.list_expiring_tokens", AsyncMock(return_value=[token])),
        patch("bot.services.mentions_poller.upsert_token", AsyncMock()) as mock_upsert,
        patch("bot.services.mentions_poller.settings") as mock_settings,
        patch("httpx.AsyncClient") as mock_httpx_cls,
    ):
        mock_settings.admin_telegram_chat_id = None  # skip notification
        mock_settings.facebook_app_id = "fb_id"
        mock_settings.facebook_app_secret = "fb_secret"
        mock_settings.canva_client_id = "canva_id"
        mock_settings.canva_client_secret = "canva_secret"
        mock_settings.google_client_id = "google_id"
        mock_settings.google_client_secret = "google_secret"
        mock_settings.tiktok_client_key = "tiktok_key"
        mock_settings.tiktok_client_secret = "tiktok_secret"

        # Mock httpx for threads/instagram (they use httpx directly)
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"access_token": "new_tok", "expires_in": 5184000}

        mock_client_instance = AsyncMock()
        mock_client_instance.get = AsyncMock(return_value=mock_response)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        mock_httpx_cls.return_value = mock_client_instance

        # Mock social_oauth refresh functions for facebook/canva/youtube/tiktok
        oauth_result = {"access_token": "new_tok", "expires_in": 5184000, "refresh_token": "new_rt"}
        with (
            patch("bot.services.social_oauth.refresh_facebook_token", MagicMock(return_value=oauth_result)),
            patch("bot.services.social_oauth.refresh_canva_token", MagicMock(return_value=oauth_result)),
            patch("bot.services.social_oauth.refresh_youtube_token", MagicMock(return_value=oauth_result)),
            patch("bot.services.social_oauth.refresh_tiktok_token", MagicMock(return_value=oauth_result)),
        ):
            from bot.services.mentions_poller import check_expiring_tokens
            await check_expiring_tokens()

        # Token was upserted (refreshed)
        assert mock_upsert.await_count >= 1


@pytest.mark.asyncio
async def test_check_expiring_tokens_notifies_on_refresh_failure(setup_test_db):
    """When refresh fails, notification is sent to admin."""
    token = _make_token("facebook")

    with (
        patch("bot.services.mentions_poller.list_expiring_tokens", AsyncMock(return_value=[token])),
        patch("bot.services.mentions_poller.upsert_token", AsyncMock()),
        patch("bot.services.mentions_poller.settings") as mock_settings,
        patch("httpx.AsyncClient") as mock_httpx_cls,
    ):
        mock_settings.admin_telegram_chat_id = "12345"
        mock_settings.telegram_bot_token = "bot_token"
        mock_settings.facebook_app_id = "fb_id"
        mock_settings.facebook_app_secret = "fb_secret"

        # Mock notification httpx client
        mock_notify_response = MagicMock()
        mock_notify_response.raise_for_status = MagicMock()
        mock_client_instance = AsyncMock()
        mock_client_instance.post = AsyncMock(return_value=mock_notify_response)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        mock_httpx_cls.return_value = mock_client_instance

        # Make refresh fail
        with patch(
            "bot.services.social_oauth.refresh_facebook_token",
            MagicMock(side_effect=RuntimeError("API error")),
        ):
            from bot.services.mentions_poller import check_expiring_tokens
            await check_expiring_tokens()

        # Notification was sent
        assert mock_client_instance.post.await_count >= 1
