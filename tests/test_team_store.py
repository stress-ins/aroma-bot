"""Tests for team_store: CRUD teams, members, invites."""
from __future__ import annotations

import pytest


class TestTeamStore:
    async def test_create_team_and_get(self):
        from bot.services.team_store import create_team, get_team

        team = await create_team("Test Team", creator_telegram_id=111)
        assert team.name == "Test Team"
        assert team.slug == "test-team"
        assert team.created_by == 111
        assert team.team_id

        fetched = await get_team(team.team_id)
        assert fetched is not None
        assert fetched.name == "Test Team"

    async def test_creator_is_owner(self):
        from bot.services.team_store import create_team, get_member_role

        team = await create_team("Owner Test", creator_telegram_id=222)
        role = await get_member_role(team.team_id, 222)
        assert role == "owner"

    async def test_get_user_teams(self):
        from bot.services.team_store import create_team, get_user_teams

        await create_team("Team A", creator_telegram_id=333)
        await create_team("Team B", creator_telegram_id=333)
        teams = await get_user_teams(333)
        assert len(teams) >= 2
        names = [t["name"] for t in teams]
        assert "Team A" in names
        assert "Team B" in names

    async def test_get_default_team_creates_personal(self):
        from bot.services.team_store import get_default_team

        team = await get_default_team(444)
        assert team is not None
        assert team.name == "Personal"
        assert team.created_by == 444

    async def test_add_member(self):
        from bot.services.team_store import create_team, add_member, get_team_members

        team = await create_team("Members Test", creator_telegram_id=555)
        await add_member(team.team_id, 556, role="editor")
        members = await get_team_members(team.team_id)
        tids = [m["telegram_id"] for m in members]
        assert 555 in tids
        assert 556 in tids
        editor = next(m for m in members if m["telegram_id"] == 556)
        assert editor["role"] == "editor"

    async def test_remove_member(self):
        from bot.services.team_store import create_team, add_member, remove_member, get_member_role

        team = await create_team("Remove Test", creator_telegram_id=666)
        await add_member(team.team_id, 667, role="viewer")
        assert await get_member_role(team.team_id, 667) == "viewer"
        removed = await remove_member(team.team_id, 667)
        assert removed is True
        assert await get_member_role(team.team_id, 667) is None

    async def test_update_role(self):
        from bot.services.team_store import create_team, add_member, update_role, get_member_role

        team = await create_team("Role Test", creator_telegram_id=777)
        await add_member(team.team_id, 778, role="viewer")
        assert await get_member_role(team.team_id, 778) == "viewer"
        await update_role(team.team_id, 778, "editor")
        assert await get_member_role(team.team_id, 778) == "editor"

    async def test_create_and_accept_invite(self):
        from bot.services.team_store import create_team, create_invite, accept_invite, get_member_role

        team = await create_team("Invite Test", creator_telegram_id=888)
        invite = await create_invite(team.team_id, created_by=888, role="editor")
        assert invite.invite_code
        assert invite.max_uses == 1

        result = await accept_invite(invite.invite_code, 889)
        assert result is not None
        assert result["joined"] is True
        assert result["role"] == "editor"
        assert await get_member_role(team.team_id, 889) == "editor"

    async def test_invite_max_uses(self):
        from bot.services.team_store import create_team, create_invite, accept_invite

        team = await create_team("Max Uses Test", creator_telegram_id=900)
        invite = await create_invite(team.team_id, created_by=900, role="viewer", max_uses=1)
        await accept_invite(invite.invite_code, 901)
        # Second use should fail
        result = await accept_invite(invite.invite_code, 902)
        assert result is None

    async def test_has_role(self):
        from bot.services.team_store import has_role

        assert has_role("owner", "viewer") is True
        assert has_role("owner", "editor") is True
        assert has_role("owner", "owner") is True
        assert has_role("editor", "owner") is False
        assert has_role("viewer", "editor") is False
        assert has_role(None, "viewer") is False

    async def test_slug_uniqueness(self):
        from bot.services.team_store import create_team

        t1 = await create_team("Dup Name", creator_telegram_id=1000)
        t2 = await create_team("Dup Name", creator_telegram_id=1001)
        assert t1.slug != t2.slug
        assert t2.slug.startswith("dup-name")
