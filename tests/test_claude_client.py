"""Tests: Claude client fallback chain (Replicate Claude → Kie.ai Gemini)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import anthropic
import pytest


_MODULE = "bot.services.claude_client"

_RATE_LIMIT = anthropic.RateLimitError(
    message="rate limited", response=MagicMock(status_code=429), body=None,
)
_BAD_REQUEST = anthropic.BadRequestError(
    message="This organization has been disabled",
    response=MagicMock(status_code=400), body=None,
)


def _make_client(exc):
    client = MagicMock()
    client.messages.create.side_effect = exc
    return client


def test_fallback_to_replicate_claude():
    """When replicate_api_key set → Replicate is tried first (before Claude API)."""
    with (
        patch(f"{_MODULE}._get_client", return_value=_make_client(_RATE_LIMIT)),
        patch(f"{_MODULE}.settings") as s,
        patch("bot.handlers.monitor.notify_owner_throttled"),
        patch(f"{_MODULE}._call_replicate_claude", return_value="replicate ok") as rep,
        patch(f"{_MODULE}._call_kie_gemini") as gem,
    ):
        s.kie_ai_api_key = "k"
        s.replicate_api_key = "r"
        s.anthropic_api_key = "a"
        from bot.services.claude_client import call_claude

        assert call_claude(messages=[{"role": "user", "content": "hi"}], max_tokens=100, retries=1) == "replicate ok"
        rep.assert_called_once()
        gem.assert_not_called()


def test_replicate_fails_then_gemini():
    """When Claude and Replicate fail → fall through to Kie.ai Gemini."""
    with (
        patch(f"{_MODULE}._get_client", return_value=_make_client(_RATE_LIMIT)),
        patch(f"{_MODULE}.settings") as s,
        patch("bot.handlers.monitor.notify_owner_throttled"),
        patch(f"{_MODULE}._call_replicate_claude", side_effect=ValueError("replicate down")),
        patch(f"{_MODULE}._call_kie_gemini", return_value="gemini ok") as gem,
    ):
        s.kie_ai_api_key = "k"
        s.replicate_api_key = "r"
        s.anthropic_api_key = "a"
        from bot.services.claude_client import call_claude

        assert call_claude(messages=[{"role": "user", "content": "hi"}], max_tokens=100, retries=1) == "gemini ok"
        gem.assert_called_once()


def test_bad_request_skips_retries():
    """BadRequestError → skip retries, go straight to fallback chain.
    With replicate_api_key set, Replicate is tried first (before Claude API).
    """
    with (
        patch(f"{_MODULE}._get_client", return_value=_make_client(_BAD_REQUEST)) as cf,
        patch(f"{_MODULE}.settings") as s,
        patch("bot.handlers.monitor.notify_owner_throttled"),
        patch(f"{_MODULE}._call_replicate_claude", return_value="rep ok") as rep,
    ):
        s.kie_ai_api_key = "k"
        s.replicate_api_key = "r"
        s.anthropic_api_key = "a"
        from bot.services.claude_client import call_claude

        assert call_claude(messages=[{"role": "user", "content": "hi"}], max_tokens=100, retries=3) == "rep ok"
        # Replicate is tried first when key is set, Claude API not called
        assert cf.return_value.messages.create.call_count == 0
        rep.assert_called_once()


def test_all_providers_fail():
    """When all providers fail → raise original Claude exception."""
    with (
        patch(f"{_MODULE}._get_client", return_value=_make_client(_RATE_LIMIT)),
        patch(f"{_MODULE}.settings") as s,
        patch("bot.handlers.monitor.notify_owner_throttled"),
        patch(f"{_MODULE}._call_replicate_claude", side_effect=ValueError("nope")),
        patch(f"{_MODULE}._call_kie_gemini", side_effect=ValueError("nope")),
    ):
        s.kie_ai_api_key = "k"
        s.replicate_api_key = "r"
        s.anthropic_api_key = "a"
        from bot.services.claude_client import call_claude

        with pytest.raises(anthropic.RateLimitError):
            call_claude(messages=[{"role": "user", "content": "hi"}], max_tokens=100, retries=1)


def test_no_fallback_without_keys():
    """When no fallback keys → raise immediately."""
    with (
        patch(f"{_MODULE}._get_client", return_value=_make_client(_RATE_LIMIT)),
        patch(f"{_MODULE}.settings") as s,
        patch("bot.handlers.monitor.notify_owner_throttled"),
        patch(f"{_MODULE}._call_replicate_claude") as rep,
        patch(f"{_MODULE}._call_kie_gemini") as gem,
    ):
        s.kie_ai_api_key = ""
        s.replicate_api_key = ""
        s.anthropic_api_key = "a"
        from bot.services.claude_client import call_claude

        with pytest.raises(anthropic.RateLimitError):
            call_claude(messages=[{"role": "user", "content": "hi"}], max_tokens=100, retries=1)
        rep.assert_not_called()
        gem.assert_not_called()
