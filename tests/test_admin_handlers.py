"""Tests for admin bot commands — access control, subscription management, promo codes.

Security-critical: verifies that non-admin users cannot access admin commands.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from tests.helpers import make_context, make_update

from bot.handlers.admin import (
    _is_admin,
    admin_costs_cmd,
    admin_promo_gen_cmd,
    admin_promo_list_cmd,
    admin_set_cmd,
    admin_users_cmd,
)

ADMIN_ID = 62912125  # from config.py
NON_ADMIN_ID = 99999


# ---------------------------------------------------------------------------
# _is_admin gate
# ---------------------------------------------------------------------------

class TestIsAdmin:
    def test_admin_id_returns_true(self, monkeypatch):
        monkeypatch.setattr("config.settings.admin_telegram_id", ADMIN_ID)
        update = make_update(user_id=ADMIN_ID)
        assert _is_admin(update) is True

    def test_non_admin_id_returns_false(self, monkeypatch):
        monkeypatch.setattr("config.settings.admin_telegram_id", ADMIN_ID)
        update = make_update(user_id=NON_ADMIN_ID)
        assert _is_admin(update) is False

    def test_no_user_returns_false(self, monkeypatch):
        monkeypatch.setattr("config.settings.admin_telegram_id", ADMIN_ID)
        update = MagicMock()
        update.effective_user = None
        assert _is_admin(update) is False


# ---------------------------------------------------------------------------
# Non-admin blocked for ALL admin commands (parametrized)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("handler", [
    admin_users_cmd,
    admin_set_cmd,
    admin_promo_gen_cmd,
    admin_promo_list_cmd,
    admin_costs_cmd,
], ids=["users", "set", "promo_gen", "promo_list", "costs"])
async def test_non_admin_blocked(handler, monkeypatch):
    """Every admin command must silently return for non-admin users."""
    monkeypatch.setattr("config.settings.admin_telegram_id", ADMIN_ID)
    update = make_update(user_id=NON_ADMIN_ID)
    ctx = make_context()

    await handler(update, ctx)

    # Non-admin: message.reply_text should NOT be called (silent return)
    update.message.reply_text.assert_not_called()


# ---------------------------------------------------------------------------
# admin_set — changes subscription
# ---------------------------------------------------------------------------

class TestAdminSet:
    async def test_admin_set_changes_subscription(self, monkeypatch):
        monkeypatch.setattr("config.settings.admin_telegram_id", ADMIN_ID)
        update = make_update(user_id=ADMIN_ID)
        ctx = make_context()
        ctx.args = ["12345", "expert", "30"]

        mock_set_sub = AsyncMock()
        monkeypatch.setattr("bot.handlers.admin.set_subscription", mock_set_sub)

        await admin_set_cmd(update, ctx)

        mock_set_sub.assert_called_once_with(12345, "expert", 30)
        reply_text = update.message.reply_text.call_args[0][0]
        assert "expert" in reply_text
        assert "12345" in reply_text

    async def test_admin_set_no_days_is_permanent(self, monkeypatch):
        monkeypatch.setattr("config.settings.admin_telegram_id", ADMIN_ID)
        update = make_update(user_id=ADMIN_ID)
        ctx = make_context()
        ctx.args = ["12345", "student"]

        mock_set_sub = AsyncMock()
        monkeypatch.setattr("bot.handlers.admin.set_subscription", mock_set_sub)

        await admin_set_cmd(update, ctx)

        mock_set_sub.assert_called_once_with(12345, "student", None)
        assert "бессрочно" in update.message.reply_text.call_args[0][0]

    async def test_admin_set_too_few_args(self, monkeypatch):
        monkeypatch.setattr("config.settings.admin_telegram_id", ADMIN_ID)
        update = make_update(user_id=ADMIN_ID)
        ctx = make_context()
        ctx.args = ["12345"]  # missing tier

        await admin_set_cmd(update, ctx)

        assert "Использование" in update.message.reply_text.call_args[0][0]

    async def test_admin_set_invalid_tier(self, monkeypatch):
        monkeypatch.setattr("config.settings.admin_telegram_id", ADMIN_ID)
        update = make_update(user_id=ADMIN_ID)
        ctx = make_context()
        ctx.args = ["12345", "premium"]  # invalid tier

        await admin_set_cmd(update, ctx)

        assert "free / student / expert" in update.message.reply_text.call_args[0][0]

    async def test_admin_set_invalid_telegram_id(self, monkeypatch):
        monkeypatch.setattr("config.settings.admin_telegram_id", ADMIN_ID)
        update = make_update(user_id=ADMIN_ID)
        ctx = make_context()
        ctx.args = ["abc", "expert"]

        await admin_set_cmd(update, ctx)

        assert "telegram_id" in update.message.reply_text.call_args[0][0].lower()


# ---------------------------------------------------------------------------
# admin_promo_gen — generates promo codes
# ---------------------------------------------------------------------------

class TestAdminPromoGen:
    async def test_creates_valid_codes(self, monkeypatch):
        monkeypatch.setattr("config.settings.admin_telegram_id", ADMIN_ID)
        update = make_update(user_id=ADMIN_ID)
        ctx = make_context()
        ctx.args = ["expert", "30", "3", "TEST"]

        fake_codes = ["TEST-ABC123", "TEST-DEF456", "TEST-GHI789"]
        monkeypatch.setattr("bot.handlers.admin.create_promo_codes", AsyncMock(return_value=fake_codes))

        await admin_promo_gen_cmd(update, ctx)

        reply_text = update.message.reply_text.call_args[0][0]
        assert "TEST-ABC123" in reply_text
        assert "expert" in reply_text

    async def test_too_few_args(self, monkeypatch):
        monkeypatch.setattr("config.settings.admin_telegram_id", ADMIN_ID)
        update = make_update(user_id=ADMIN_ID)
        ctx = make_context()
        ctx.args = ["expert"]  # missing days

        await admin_promo_gen_cmd(update, ctx)

        assert "Использование" in update.message.reply_text.call_args[0][0]

    async def test_invalid_tier_rejected(self, monkeypatch):
        monkeypatch.setattr("config.settings.admin_telegram_id", ADMIN_ID)
        update = make_update(user_id=ADMIN_ID)
        ctx = make_context()
        ctx.args = ["free", "30"]  # free not allowed for promo

        await admin_promo_gen_cmd(update, ctx)

        assert "student / expert" in update.message.reply_text.call_args[0][0]

    async def test_max_50_codes_limit(self, monkeypatch):
        monkeypatch.setattr("config.settings.admin_telegram_id", ADMIN_ID)
        update = make_update(user_id=ADMIN_ID)
        ctx = make_context()
        ctx.args = ["expert", "30", "100"]  # >50

        await admin_promo_gen_cmd(update, ctx)

        assert "50" in update.message.reply_text.call_args[0][0]


# ---------------------------------------------------------------------------
# admin_users — lists users
# ---------------------------------------------------------------------------

class TestAdminUsers:
    async def test_lists_users(self, monkeypatch):
        monkeypatch.setattr("config.settings.admin_telegram_id", ADMIN_ID)
        update = make_update(user_id=ADMIN_ID)
        ctx = make_context()
        ctx.args = []

        from datetime import datetime, timezone
        mock_user = MagicMock()
        mock_user.telegram_id = 12345
        mock_user.tier = "expert"
        mock_user.trial_ends_at = datetime(2026, 4, 1, tzinfo=timezone.utc)
        mock_user.created_at = datetime(2026, 3, 1, tzinfo=timezone.utc)

        monkeypatch.setattr("bot.handlers.admin.list_users", AsyncMock(return_value=[mock_user]))

        await admin_users_cmd(update, ctx)

        reply_text = update.message.reply_text.call_args[0][0]
        assert "12345" in reply_text
        assert "expert" in reply_text

    async def test_empty_user_list(self, monkeypatch):
        monkeypatch.setattr("config.settings.admin_telegram_id", ADMIN_ID)
        update = make_update(user_id=ADMIN_ID)
        ctx = make_context()
        ctx.args = []

        monkeypatch.setattr("bot.handlers.admin.list_users", AsyncMock(return_value=[]))

        await admin_users_cmd(update, ctx)

        assert "не найден" in update.message.reply_text.call_args[0][0].lower()


# ---------------------------------------------------------------------------
# admin_promo_list
# ---------------------------------------------------------------------------

class TestAdminPromoList:
    async def test_lists_promo_codes(self, monkeypatch):
        monkeypatch.setattr("config.settings.admin_telegram_id", ADMIN_ID)
        update = make_update(user_id=ADMIN_ID)
        ctx = make_context()

        from datetime import datetime, timezone
        mock_promo = MagicMock()
        mock_promo.code = "AROMA-XYZ"
        mock_promo.tier = "expert"
        mock_promo.duration_days = 30
        mock_promo.uses_count = 0
        mock_promo.max_uses = 1
        mock_promo.expires_at = datetime(2026, 12, 31, tzinfo=timezone.utc)

        monkeypatch.setattr("bot.handlers.admin.list_promo_codes", AsyncMock(return_value=[mock_promo]))

        await admin_promo_list_cmd(update, ctx)

        reply_text = update.message.reply_text.call_args[0][0]
        assert "AROMA-XYZ" in reply_text

    async def test_empty_promo_list(self, monkeypatch):
        monkeypatch.setattr("config.settings.admin_telegram_id", ADMIN_ID)
        update = make_update(user_id=ADMIN_ID)
        ctx = make_context()

        monkeypatch.setattr("bot.handlers.admin.list_promo_codes", AsyncMock(return_value=[]))

        await admin_promo_list_cmd(update, ctx)

        assert "не найден" in update.message.reply_text.call_args[0][0].lower()
