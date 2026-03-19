"""Tests: Claude client — Replicate Claude primary, direct Claude API fallback."""
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


def test_replicate_primary():
    """When replicate_api_key set → Replicate is the only provider used."""
    with (
        patch(f"{_MODULE}._get_client", return_value=_make_client(_RATE_LIMIT)) as cf,
        patch(f"{_MODULE}.settings") as s,
        patch("bot.handlers.monitor.notify_owner_throttled"),
        patch(f"{_MODULE}._call_replicate_claude", return_value="replicate ok") as rep,
    ):
        s.replicate_api_key = "r"
        s.anthropic_api_key = "a"
        from bot.services.claude_client import call_claude

        assert call_claude(messages=[{"role": "user", "content": "hi"}], max_tokens=100, retries=1) == "replicate ok"
        rep.assert_called_once()
        # Direct Claude API should not be touched when Replicate key is present
        assert cf.return_value.messages.create.call_count == 0


def test_replicate_retries_then_raises():
    """When Replicate fails all attempts → raise, no Gemini fallback."""
    with (
        patch(f"{_MODULE}._get_client", return_value=_make_client(_RATE_LIMIT)),
        patch(f"{_MODULE}.settings") as s,
        patch("bot.handlers.monitor.notify_owner_throttled"),
        patch(f"{_MODULE}._call_replicate_claude", side_effect=ValueError("replicate down")),
    ):
        s.replicate_api_key = "r"
        s.anthropic_api_key = "a"
        from bot.services.claude_client import call_claude

        with pytest.raises(ValueError, match="replicate down"):
            call_claude(messages=[{"role": "user", "content": "hi"}], max_tokens=100, retries=2)


def test_direct_claude_when_no_replicate_key():
    """When no replicate key → falls through to direct Claude API."""
    response = MagicMock()
    response.content = [MagicMock(text="direct ok")]
    response.usage.input_tokens = 10
    response.usage.output_tokens = 5
    client = MagicMock()
    client.messages.create.return_value = response

    with (
        patch(f"{_MODULE}._get_client", return_value=client),
        patch(f"{_MODULE}.settings") as s,
        patch("bot.handlers.monitor.notify_owner_throttled"),
    ):
        s.replicate_api_key = ""
        s.anthropic_api_key = "a"
        from bot.services.claude_client import call_claude

        assert call_claude(messages=[{"role": "user", "content": "hi"}], max_tokens=100, retries=1) == "direct ok"


def test_bad_request_raises_immediately():
    """BadRequestError (org disabled) → no retries, raise immediately."""
    with (
        patch(f"{_MODULE}._get_client", return_value=_make_client(_BAD_REQUEST)),
        patch(f"{_MODULE}.settings") as s,
        patch("bot.handlers.monitor.notify_owner_throttled"),
    ):
        s.replicate_api_key = ""
        s.anthropic_api_key = "a"
        from bot.services.claude_client import call_claude

        with pytest.raises(anthropic.BadRequestError):
            call_claude(messages=[{"role": "user", "content": "hi"}], max_tokens=100, retries=3)


def test_replicate_nested_list_output():
    """Replicate sometimes returns nested lists [['chunk1'], ['chunk2']] — must flatten."""
    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.raise_for_status = MagicMock()
    fake_resp.json.return_value = {
        "status": "succeeded",
        "output": [["Hello "], ["world"]],
    }

    with (
        patch("httpx.post", return_value=fake_resp),
        patch(f"{_MODULE}.settings") as s,
        patch(f"{_MODULE}._log_cost_sync"),
        patch(f"{_MODULE}.current_telegram_id", MagicMock(get=MagicMock(return_value=0))),
    ):
        s.replicate_api_key = "r8_test"
        from bot.services.claude_client import _call_replicate_claude

        result = _call_replicate_claude(
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=100,
            context="test",
        )
        assert result == "Hello world"


def test_no_fallback_without_keys():
    """When no keys at all → raise immediately."""
    with (
        patch(f"{_MODULE}._get_client", return_value=_make_client(_RATE_LIMIT)),
        patch(f"{_MODULE}.settings") as s,
        patch("bot.handlers.monitor.notify_owner_throttled"),
    ):
        s.replicate_api_key = ""
        s.anthropic_api_key = "a"
        from bot.services.claude_client import call_claude

        with pytest.raises(anthropic.RateLimitError):
            call_claude(messages=[{"role": "user", "content": "hi"}], max_tokens=100, retries=1)
