"""Tests for the global error handler — ensures errors are caught and users see a message."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from tests.helpers import make_context


class TestErrorHandler:
    async def test_replies_to_user_on_error(self, monkeypatch):
        """Error handler sends an error message to the user."""
        from telegram import Update
        from bot.handlers import monitor
        monkeypatch.setattr(monitor, "notify_owner", MagicMock())

        from bot.handlers.errors import error_handler

        update = MagicMock(spec=Update)
        update.effective_message.reply_text = AsyncMock()
        update.effective_user.id = 12345
        update.effective_message.text = "/content"

        ctx = make_context()
        ctx.error = ValueError("test error")

        await error_handler(update, ctx)

        update.effective_message.reply_text.assert_called_once()
        text = update.effective_message.reply_text.call_args[0][0]
        assert "ошибка" in text.lower()

    async def test_no_crash_when_reply_fails(self, monkeypatch):
        """Error handler doesn't raise if reply_text itself fails."""
        from bot.handlers import monitor
        monkeypatch.setattr(monitor, "notify_owner", MagicMock())

        from bot.handlers.errors import error_handler

        update = MagicMock()
        update.effective_message.reply_text = AsyncMock(side_effect=Exception("network"))
        update.effective_user.id = 12345

        ctx = make_context()
        ctx.error = RuntimeError("boom")

        # Should NOT raise
        await error_handler(update, ctx)

    async def test_handles_non_update_gracefully(self, monkeypatch):
        """Error handler works when update is not a real Update object."""
        from bot.handlers import monitor
        monkeypatch.setattr(monitor, "notify_owner", MagicMock())

        from bot.handlers.errors import error_handler

        ctx = make_context()
        ctx.error = RuntimeError("background error")

        await error_handler("not-an-update", ctx)

    async def test_notifies_owner_via_monitor(self, monkeypatch):
        """Error handler attempts to notify the owner."""
        from telegram import Update
        from bot.handlers import monitor
        mock_notify = MagicMock()
        monkeypatch.setattr(monitor, "notify_owner", mock_notify)

        from bot.handlers.errors import error_handler

        update = MagicMock(spec=Update)
        update.effective_message.reply_text = AsyncMock()
        update.effective_user.id = 12345
        update.effective_message.text = "/content"

        ctx = make_context()
        ctx.error = ValueError("test error")

        await error_handler(update, ctx)

        mock_notify.assert_called_once()
        msg = mock_notify.call_args[0][0]
        assert "ValueError" in msg
