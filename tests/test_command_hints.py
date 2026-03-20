"""Tests for Telegram command hint registration (set_my_commands)."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from bot.application import USER_COMMANDS, ADMIN_EXTRA_COMMANDS, _post_init


@pytest.mark.asyncio
async def test_post_init_registers_user_commands():
    bot = AsyncMock()
    app = AsyncMock()
    app.bot = bot

    await _post_init(app)

    # set_my_commands called twice: once for users, once for admin
    assert bot.set_my_commands.call_count == 2

    user_call = bot.set_my_commands.call_args_list[0]
    assert user_call.args[0] == USER_COMMANDS

    admin_call = bot.set_my_commands.call_args_list[1]
    assert admin_call.args[0] == USER_COMMANDS + ADMIN_EXTRA_COMMANDS


@pytest.mark.asyncio
async def test_post_init_sets_descriptions():
    bot = AsyncMock()
    app = AsyncMock()
    app.bot = bot

    await _post_init(app)

    bot.set_my_short_description.assert_called_once()
    bot.set_my_description.assert_called_once()

    short = bot.set_my_short_description.call_args.kwargs.get(
        "short_description"
    ) or bot.set_my_short_description.call_args.args[0]
    assert "ароматерапии" in short.lower()


def test_user_commands_have_unique_names():
    names = [c.command for c in USER_COMMANDS]
    assert len(names) == len(set(names))


def test_admin_commands_dont_overlap_user():
    user_names = {c.command for c in USER_COMMANDS}
    admin_names = {c.command for c in ADMIN_EXTRA_COMMANDS}
    assert user_names.isdisjoint(admin_names)


def test_monitor_commands_list():
    from monitor_bot import MONITOR_COMMANDS

    names = [c.command for c in MONITOR_COMMANDS]
    assert "status" in names
    assert "help" in names
    assert len(names) == len(set(names))
