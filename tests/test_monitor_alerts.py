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
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = RuntimeError("test API error")

        with (
            patch("bot.handlers.monitor.notify_owner") as mock_owner,
            patch("bot.handlers.monitor._recent_alerts", {}),
            patch("anthropic.Anthropic", return_value=mock_client),
        ):
            from bot.services.claude_client import call_claude

            with pytest.raises(RuntimeError, match="test API error"):
                call_claude(
                    messages=[{"role": "user", "content": "hi"}],
                    max_tokens=100,
                    context="test context",
                )
            mock_owner.assert_called_once()
            call_text = mock_owner.call_args[0][0]
            assert "Claude API error" in call_text
            assert "test context" in call_text


class TestImageGenNotifies:
    def test_image_gen_failure_notifies(self):
        """Image gen failure sends throttled notification on submit error."""
        from bot.services.gemini_images import generate_gemini_image_sync

        with (
            patch("bot.handlers.monitor.notify_owner") as mock_owner,
            patch("bot.handlers.monitor._recent_alerts", {}),
            patch("httpx.Client") as mock_client_cls,
        ):
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.side_effect = RuntimeError("connection refused")
            mock_client_cls.return_value = mock_client

            result = generate_gemini_image_sync("test prompt", log_context="test image")

        assert result is None
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
