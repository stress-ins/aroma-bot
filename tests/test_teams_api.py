"""Tests for team management API endpoints."""
from __future__ import annotations

import pytest


class TestTeamsApi:
    """Tests for /api/teams endpoints using team_store directly."""

    async def test_create_team_via_store(self):
        from bot.services.team_store import create_team, get_user_teams

        team = await create_team("API Test", creator_telegram_id=5001)
        assert team.name == "API Test"
        teams = await get_user_teams(5001)
        assert any(t["team_id"] == team.team_id for t in teams)

    async def test_invite_flow(self):
        from bot.services.team_store import (
            create_team, create_invite, accept_invite, get_member_role,
        )

        team = await create_team("Invite Flow", creator_telegram_id=5002)
        invite = await create_invite(team.team_id, created_by=5002, role="editor")
        assert invite.invite_code

        result = await accept_invite(invite.invite_code, 5003)
        assert result["joined"] is True
        assert result["role"] == "editor"
        assert await get_member_role(team.team_id, 5003) == "editor"

    async def test_deep_link_invite_code(self):
        from bot.services.team_store import create_team, create_invite

        team = await create_team("Deep Link", creator_telegram_id=5004)
        invite = await create_invite(team.team_id, created_by=5004)
        assert len(invite.invite_code) > 10  # url-safe token

    async def test_team_rename(self):
        from bot.services.team_store import create_team, get_team
        from sqlalchemy import update as sa_update
        from db.models import TeamModel
        from db.session import AsyncSessionLocal

        team = await create_team("Old Name", creator_telegram_id=5005)
        async with AsyncSessionLocal() as session:
            await session.execute(
                sa_update(TeamModel)
                .where(TeamModel.team_id == team.team_id)
                .values(name="New Name")
            )
            await session.commit()
        updated = await get_team(team.team_id)
        assert updated.name == "New Name"

    async def test_leave_team(self):
        from bot.services.team_store import (
            create_team, add_member, remove_member, get_member_role,
        )

        team = await create_team("Leave Test", creator_telegram_id=5006)
        await add_member(team.team_id, 5007, role="editor")
        assert await get_member_role(team.team_id, 5007) == "editor"
        await remove_member(team.team_id, 5007)
        assert await get_member_role(team.team_id, 5007) is None


class TestTeamsRouter:
    """Verify the router module is importable and has expected endpoints."""

    def test_router_exists(self):
        from miniapp.api.routers.teams import router
        routes = [r.path for r in router.routes]
        assert "/api/teams" in routes
        assert "/api/teams/{team_id}" in routes
        assert "/api/teams/{team_id}/members" in routes
        assert "/api/teams/{team_id}/invites" in routes
        assert "/api/invites/{invite_code}/accept" in routes

    def test_teams_js_module_exists(self):
        from pathlib import Path
        js = Path("miniapp/static/js/teams.js").read_text(encoding="utf-8")
        assert "createTeamsModule" in js
        assert "renderTeamSettings" in js
        assert "renderTeamSwitcher" in js
        assert "switchTeam" in js
