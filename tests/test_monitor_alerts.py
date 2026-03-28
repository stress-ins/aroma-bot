from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest


class TestNotifyOwnerThrottled:
    def setup_method(self):
        from bot.handlers.monitor import _recent_alerts
        _recent_alerts.clear()

    def test_throttle_dedup(self):
        """Same dedup key within cooldown \u2014 only one call goes through."""
        from bot.handlers.monitor import notify_owner_throttled

        with patch("bot.handlers.monitor.notify_owner") as mock_notify:
            notify_owner_throttled("msg1", dedup_key="key1", cooldown=300)
            notify_owner_throttled("msg2", dedup_key="key1", cooldown=300)
            assert mock_notify.call_count == 1

    def test_throttle_different_keys(self):
        """Different dedup keys \u2014 both go through."""
        from bot.handlers.monitor import notify_owner_throttled

        with patch("bot.handlers.monitor.notify_owner") as mock_notify:
            notify_owner_throttled("msg1", dedup_key="key1", cooldown=300)
            notify_owner_throttled("msg2", dedup_key="key2", cooldown=300)
            assert mock_notify.call_count == 2

    def test_throttle_expired_cooldown(self):
        """After cooldown expires, same key goes through again."""
        from bot.handlers import monitor
        from bot.handlers.monitor import notify_owner_throttled

        with patch("bot.handlers.monitor.notify_owner") as mock_notify:
            notify_owner_throttled("msg1", dedup_key="key1", cooldown=1)
            monitor._recent_alerts["key1"] = time.time() - 2
            notify_owner_throttled("msg2", dedup_key="key1", cooldown=1)
            assert mock_notify.call_count == 2


class TestClaudeClientNotifies:
    def test_claude_wrapper_notifies_and_reraises(self):
        """Claude wrapper sends notification and re-raises on API error."""
        import bot.services.claude_client as cc_mod

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = RuntimeError("test API error")

        old_client = cc_mod._client
        try:
            cc_mod._client = mock_client

            with (
                patch("bot.handlers.monitor.notify_owner") as mock_owner,
                patch("bot.handlers.monitor._recent_alerts", {}),
                patch("bot.services.claude_client.settings") as mock_settings,
            ):
                mock_settings.anthropic_api_key = "fake"
                mock_settings.replicate_api_key = ""
                mock_settings.kie_ai_api_key = ""
                with pytest.raises(RuntimeError, match="test API error"):
                    cc_mod.call_claude(
                        messages=[{"role": "user", "content": "hi"}],
                        max_tokens=100,
                        context="test context",
                    )
                mock_owner.assert_called_once()
                call_text = mock_owner.call_args[0][0]
                assert "Claude API error" in call_text
                assert "test context" in call_text
        finally:
            cc_mod._client = old_client


class TestImageGenNotifies:
    def test_image_gen_failure_notifies(self):
        """Image gen failure sends throttled notification on submit error."""
        from bot.services.gemini_images import generate_gemini_image_sync

        with (
            patch("bot.handlers.monitor.notify_owner") as mock_owner,
            patch("bot.handlers.monitor._recent_alerts", {}),
            patch("bot.services.gemini_images.settings") as mock_settings,
            patch("httpx.Client") as mock_client_cls,
        ):
            mock_settings.kie_ai_api_key = "fake-kie-key"
            mock_settings.nana_banana_api_key = ""
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.side_effect = RuntimeError("connection refused")
            mock_client_cls.return_value = mock_client

            result = generate_gemini_image_sync("test prompt", log_context="test image")

        assert result.image_bytes is None
        assert mock_owner.call_count >= 1
        call_text = mock_owner.call_args[0][0]
        assert "Image gen failed" in call_text
        assert "test image" in call_text

    def test_no_notification_without_config(self):
        """No crash when monitor bot is not configured."""
        from bot.handlers.monitor import notify_owner

        with patch("config.settings") as mock_settings:
            mock_settings.monitor_bot_token = ""
            mock_settings.monitor_chat_id = ""
            notify_owner("test message")


class TestRecentAlertsCleanup:
    def setup_method(self):
        from bot.handlers.monitor import _recent_alerts
        _recent_alerts.clear()

    def test_cleanup_limits_size(self):
        """_recent_alerts should not grow beyond _RECENT_ALERTS_MAX."""
        from bot.handlers.monitor import (
            _recent_alerts,
            _RECENT_ALERTS_MAX,
            notify_owner_throttled,
        )
        import time

        # Fill beyond max with unique keys
        now = time.time()
        for i in range(_RECENT_ALERTS_MAX + 100):
            _recent_alerts[f"key_{i}"] = now - 100000  # old timestamps

        with patch("bot.handlers.monitor.notify_owner"):
            notify_owner_throttled("trigger cleanup", dedup_key="trigger", cooldown=1)

        assert len(_recent_alerts) <= _RECENT_ALERTS_MAX + 1  # +1 for the trigger key
