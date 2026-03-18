"""Tests for OAuth social connect handlers — Threads & Instagram.

Security-critical: verifies OAuth URL generation, state validation, and token handling.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from tests.helpers import make_context, make_update

from bot.handlers.social_connect import cmd_instagram_connect, cmd_threads_connect
from bot.services.social_oauth import (
    OAuthStateError,
    build_oauth_state,
    parse_oauth_state,
)


# ---------------------------------------------------------------------------
# OAuth URL generation for Threads
# ---------------------------------------------------------------------------

class TestThreadsConnect:
    async def test_generates_url_with_button(self, monkeypatch):
        monkeypatch.setattr("config.settings.threads_app_id", "test-app-id")
        monkeypatch.setattr("config.settings.threads_app_secret", "test-secret")
        monkeypatch.setattr("config.settings.telegram_bot_token", "test-bot-token")
        update = make_update(text="/threads_connect")
        ctx = make_context()

        await cmd_threads_connect(update, ctx)

        call_args = update.message.reply_text.call_args
        text = call_args[0][0]
        assert "Threads" in text
        # Verify InlineKeyboard with URL button
        kb = call_args[1]["reply_markup"]
        all_buttons = [btn for row in kb.inline_keyboard for btn in row]
        assert len(all_buttons) == 1
        btn = all_buttons[0]
        assert "threads.net" in btn.url
        assert "test-app-id" in btn.url
        assert "Подключить" in btn.text

    async def test_missing_app_id_shows_error(self, monkeypatch):
        monkeypatch.setattr("config.settings.threads_app_id", "")
        monkeypatch.setattr("config.settings.threads_app_secret", "")
        update = make_update(text="/threads_connect")
        ctx = make_context()

        await cmd_threads_connect(update, ctx)

        text = update.message.reply_text.call_args[0][0]
        assert "не настроен" in text.lower() or "THREADS_APP_ID" in text


# ---------------------------------------------------------------------------
# OAuth URL generation for Instagram
# ---------------------------------------------------------------------------

class TestInstagramConnect:
    async def test_generates_url_with_button(self, monkeypatch):
        monkeypatch.setattr("config.settings.instagram_app_id", "ig-app-id")
        monkeypatch.setattr("config.settings.instagram_app_secret", "ig-secret")
        monkeypatch.setattr("config.settings.telegram_bot_token", "test-bot-token")
        update = make_update(text="/instagram_connect")
        ctx = make_context()

        await cmd_instagram_connect(update, ctx)

        call_args = update.message.reply_text.call_args
        text = call_args[0][0]
        assert "Instagram" in text
        kb = call_args[1]["reply_markup"]
        all_buttons = [btn for row in kb.inline_keyboard for btn in row]
        assert len(all_buttons) == 1
        btn = all_buttons[0]
        assert "instagram.com" in btn.url
        assert "ig-app-id" in btn.url

    async def test_missing_app_id_shows_error(self, monkeypatch):
        monkeypatch.setattr("config.settings.instagram_app_id", "")
        monkeypatch.setattr("config.settings.instagram_app_secret", "")
        update = make_update(text="/instagram_connect")
        ctx = make_context()

        await cmd_instagram_connect(update, ctx)

        text = update.message.reply_text.call_args[0][0]
        assert "не настроен" in text.lower() or "INSTAGRAM_APP_ID" in text


# ---------------------------------------------------------------------------
# OAuth state — build & parse (tests the crypto layer)
# ---------------------------------------------------------------------------

class TestOAuthState:
    def test_build_and_parse_roundtrip(self):
        secret = "test-bot-token"
        state = build_oauth_state(
            secret=secret,
            service="threads",
            chat_id=12345,
            user_id=67890,
        )
        parsed = parse_oauth_state(state=state, secret=secret, max_age_seconds=3600)
        assert parsed.service == "threads"
        assert parsed.chat_id == "12345"
        assert parsed.user_id == "67890"

    def test_invalid_signature_rejected(self):
        secret = "test-bot-token"
        state = build_oauth_state(
            secret=secret,
            service="threads",
            chat_id=12345,
            user_id=67890,
        )
        with pytest.raises(OAuthStateError, match="signature"):
            parse_oauth_state(state=state, secret="wrong-secret", max_age_seconds=3600)

    def test_malformed_state_rejected(self):
        with pytest.raises(OAuthStateError):
            parse_oauth_state(state="not.a.valid.state", secret="x", max_age_seconds=3600)

    def test_expired_state_rejected(self, monkeypatch):
        import time as _time
        secret = "test-bot-token"
        # Build state at time T
        state = build_oauth_state(
            secret=secret,
            service="threads",
            chat_id=12345,
            user_id=67890,
        )
        # Advance clock by 2 hours so state is expired
        real_time = _time.time
        monkeypatch.setattr(_time, "time", lambda: real_time() + 7200)
        with pytest.raises(OAuthStateError, match="expired"):
            parse_oauth_state(state=state, secret=secret, max_age_seconds=3600)

    def test_state_contains_required_fields(self):
        secret = "test-bot-token"
        state = build_oauth_state(
            secret=secret,
            service="instagram",
            chat_id=111,
            user_id=222,
        )
        # State should be two base64 parts separated by dot
        parts = state.split(".")
        assert len(parts) == 2
        # Both parts should be non-empty
        assert all(parts)
