"""Tests: Claude client fallback chain (Kie.ai Claude → Kie.ai Gemini)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import anthropic
import pytest


_MODULE = "bot.services.claude_client"


def test_claude_fallback_to_kie_claude():
    """When Claude retries exhausted → fallback to Kie.ai Claude first."""
    with (
        patch(f"{_MODULE}._get_client") as mock_client_fn,
        patch(f"{_MODULE}.settings") as mock_settings,
        patch("bot.handlers.monitor.notify_owner_throttled", return_value=None) as mock_notify,
        patch(f"{_MODULE}._call_kie_claude", return_value="kie claude response") as mock_kie_claude,
        patch(f"{_MODULE}._call_kie_gemini") as mock_kie_gemini,
    ):
        mock_settings.kie_ai_api_key = "test-key"
        mock_settings.anthropic_api_key = "test"

        client = MagicMock()
        client.messages.create.side_effect = anthropic.RateLimitError(
            message="rate limited",
            response=MagicMock(status_code=429),
            body=None,
        )
        mock_client_fn.return_value = client

        from bot.services.claude_client import call_claude

        result = call_claude(
            messages=[{"role": "user", "content": "hello"}],
            max_tokens=100,
            context="test-fallback",
            retries=1,
        )

        assert result == "kie claude response"
        mock_kie_claude.assert_called_once()
        mock_kie_gemini.assert_not_called()
        assert any("kie.ai claude" in str(c).lower() for c in mock_notify.call_args_list)


def test_kie_claude_then_kie_gemini():
    """When both Claude and Kie.ai Claude fail → fallback to Kie.ai Gemini."""
    with (
        patch(f"{_MODULE}._get_client") as mock_client_fn,
        patch(f"{_MODULE}.settings") as mock_settings,
        patch("bot.handlers.monitor.notify_owner_throttled", return_value=None),
        patch(f"{_MODULE}._call_kie_claude", side_effect=ValueError("kie claude failed")),
        patch(f"{_MODULE}._call_kie_gemini", return_value="gemini response") as mock_kie_gemini,
    ):
        mock_settings.kie_ai_api_key = "test-key"
        mock_settings.anthropic_api_key = "test"

        client = MagicMock()
        client.messages.create.side_effect = anthropic.RateLimitError(
            message="rate limited",
            response=MagicMock(status_code=429),
            body=None,
        )
        mock_client_fn.return_value = client

        from bot.services.claude_client import call_claude

        result = call_claude(
            messages=[{"role": "user", "content": "hello"}],
            max_tokens=100,
            context="test-kie-chain",
            retries=1,
        )

        assert result == "gemini response"
        mock_kie_gemini.assert_called_once()


def test_bad_request_error_triggers_fallback():
    """BadRequestError (e.g. org disabled) → skip retries, go straight to fallback."""
    with (
        patch(f"{_MODULE}._get_client") as mock_client_fn,
        patch(f"{_MODULE}.settings") as mock_settings,
        patch("bot.handlers.monitor.notify_owner_throttled", return_value=None),
        patch(f"{_MODULE}._call_kie_claude", return_value="kie response") as mock_kie_claude,
    ):
        mock_settings.kie_ai_api_key = "test-key"
        mock_settings.anthropic_api_key = "test"

        client = MagicMock()
        client.messages.create.side_effect = anthropic.BadRequestError(
            message="This organization has been disabled",
            response=MagicMock(status_code=400),
            body=None,
        )
        mock_client_fn.return_value = client

        from bot.services.claude_client import call_claude

        result = call_claude(
            messages=[{"role": "user", "content": "hello"}],
            max_tokens=100,
            context="test-bad-request",
            retries=3,
        )

        assert result == "kie response"
        # Should only have been called once (no retries for BadRequestError)
        assert client.messages.create.call_count == 1
        mock_kie_claude.assert_called_once()


def test_claude_and_kie_both_fail():
    """When Claude, Kie.ai Claude, and Kie.ai Gemini all fail → raise original exception."""
    with (
        patch(f"{_MODULE}._get_client") as mock_client_fn,
        patch(f"{_MODULE}.settings") as mock_settings,
        patch("bot.handlers.monitor.notify_owner_throttled"),
        patch(f"{_MODULE}._call_kie_claude", side_effect=ValueError("kie claude failed")),
        patch(f"{_MODULE}._call_kie_gemini", side_effect=ValueError("kie gemini failed")),
    ):
        mock_settings.kie_ai_api_key = "test-key"
        mock_settings.anthropic_api_key = "test"

        client = MagicMock()
        client.messages.create.side_effect = anthropic.RateLimitError(
            message="rate limited",
            response=MagicMock(status_code=429),
            body=None,
        )
        mock_client_fn.return_value = client

        from bot.services.claude_client import call_claude

        with pytest.raises(anthropic.RateLimitError):
            call_claude(
                messages=[{"role": "user", "content": "hello"}],
                max_tokens=100,
                context="test-all-fail",
                retries=1,
            )


def test_no_fallback_without_kie_key():
    """When kie_ai_api_key is empty → no fallback, raise immediately."""
    with (
        patch(f"{_MODULE}._get_client") as mock_client_fn,
        patch(f"{_MODULE}.settings") as mock_settings,
        patch("bot.handlers.monitor.notify_owner_throttled"),
        patch(f"{_MODULE}._call_kie_claude") as mock_kie_claude,
        patch(f"{_MODULE}._call_kie_gemini") as mock_kie_gemini,
    ):
        mock_settings.kie_ai_api_key = ""
        mock_settings.anthropic_api_key = "test"

        client = MagicMock()
        client.messages.create.side_effect = anthropic.RateLimitError(
            message="rate limited",
            response=MagicMock(status_code=429),
            body=None,
        )
        mock_client_fn.return_value = client

        from bot.services.claude_client import call_claude

        with pytest.raises(anthropic.RateLimitError):
            call_claude(
                messages=[{"role": "user", "content": "hello"}],
                max_tokens=100,
                context="test-no-key",
                retries=1,
            )

        mock_kie_claude.assert_not_called()
        mock_kie_gemini.assert_not_called()
