"""Tests for team auth context resolution."""
from __future__ import annotations

import pytest
from miniapp.api.auth import TeamContext, require_team_role
from bot.services.team_store import has_role


class TestTeamContext:
    def test_team_context_dataclass(self):
        ctx = TeamContext(telegram_id=123, team_id="abc", role="editor")
        assert ctx.telegram_id == 123
        assert ctx.team_id == "abc"
        assert ctx.role == "editor"


class TestRequireTeamRole:
    def test_has_role_logic(self):
        assert has_role("owner", "viewer") is True
        assert has_role("owner", "editor") is True
        assert has_role("owner", "owner") is True
        assert has_role("editor", "editor") is True
        assert has_role("editor", "viewer") is True
        assert has_role("editor", "owner") is False
        assert has_role("viewer", "viewer") is True
        assert has_role("viewer", "editor") is False
        assert has_role(None, "viewer") is False
