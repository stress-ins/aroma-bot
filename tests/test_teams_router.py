"""Tests for teams router — CRUD teams, members, roles, invites."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _bypass_auth(monkeypatch):
    monkeypatch.setenv("AROMA_BYPASS_AUTH", "1")


OWNER_ID = 12345
OTHER_ID = 67890
VIEWER_ID = 11111

OWNER_HEADERS = {
    "X-Telegram-Init-Data": 'user=%7B%22id%22%3A12345%2C%22username%22%3A%22owner_user%22%7D&auth_date=9999999999&hash=abc',
}
OTHER_HEADERS = {
    "X-Telegram-Init-Data": 'user=%7B%22id%22%3A67890%2C%22username%22%3A%22other_user%22%7D&auth_date=9999999999&hash=abc',
}
VIEWER_HEADERS = {
    "X-Telegram-Init-Data": 'user=%7B%22id%22%3A11111%2C%22username%22%3A%22viewer_user%22%7D&auth_date=9999999999&hash=abc',
}
STRANGER_HEADERS = {
    "X-Telegram-Init-Data": 'user=%7B%22id%22%3A99999%2C%22username%22%3A%22stranger%22%7D&auth_date=9999999999&hash=abc',
}


def _client() -> TestClient:
    from miniapp_server import app
    return TestClient(app)


@pytest.fixture()
async def team(setup_test_db):
    """Create a team owned by OWNER_ID with OTHER_ID as editor."""
    from bot.services.team_store import create_team, add_member
    t = await create_team("Test Team", OWNER_ID, creator_username="owner_user")
    await add_member(t.team_id, OTHER_ID, role="editor", username="other_user")
    return t


# ---------------------------------------------------------------------------
# GET /api/teams — list user teams
# ---------------------------------------------------------------------------


class TestListTeams:
    async def test_list_teams_returns_items(self, team):
        client = _client()
        resp = client.get("/api/teams", headers=OWNER_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert len(data["items"]) >= 1
        names = [t["name"] for t in data["items"]]
        assert "Test Team" in names

    async def test_list_teams_empty_for_stranger(self, setup_test_db):
        client = _client()
        resp = client.get("/api/teams", headers=STRANGER_HEADERS)
        assert resp.status_code == 200
        assert resp.json()["items"] == []


# ---------------------------------------------------------------------------
# POST /api/teams — create team
# ---------------------------------------------------------------------------


class TestCreateTeam:
    async def test_create_team(self, setup_test_db):
        client = _client()
        resp = client.post(
            "/api/teams",
            json={"name": "New Team"},
            headers=OWNER_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "New Team"
        assert "team_id" in data
        assert "slug" in data

    async def test_create_team_empty_name_rejected(self, setup_test_db):
        client = _client()
        resp = client.post(
            "/api/teams",
            json={"name": "   "},
            headers=OWNER_HEADERS,
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "name_required"


# ---------------------------------------------------------------------------
# GET /api/teams/{team_id} — team detail
# ---------------------------------------------------------------------------


class TestGetTeamDetail:
    async def test_get_team_detail_as_member(self, team):
        client = _client()
        resp = client.get(f"/api/teams/{team.team_id}", headers=OWNER_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["team_id"] == team.team_id
        assert data["name"] == "Test Team"
        assert data["role"] == "owner"
        assert "members" in data
        assert "connected_accounts" in data

    async def test_get_team_detail_forbidden_for_non_member(self, team):
        client = _client()
        resp = client.get(f"/api/teams/{team.team_id}", headers=STRANGER_HEADERS)
        assert resp.status_code == 403
        assert resp.json()["detail"] == "not_a_team_member"


# ---------------------------------------------------------------------------
# PATCH /api/teams/{team_id} — rename team (owner only)
# ---------------------------------------------------------------------------


class TestRenameTeam:
    async def test_rename_team_as_owner(self, team):
        client = _client()
        resp = client.patch(
            f"/api/teams/{team.team_id}",
            json={"name": "Renamed Team"},
            headers={**OWNER_HEADERS, "X-Team-Id": team.team_id},
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        # Verify rename persisted
        detail = client.get(f"/api/teams/{team.team_id}", headers=OWNER_HEADERS)
        assert detail.json()["name"] == "Renamed Team"

    async def test_rename_team_forbidden_for_editor(self, team):
        client = _client()
        resp = client.patch(
            f"/api/teams/{team.team_id}",
            json={"name": "Hacked Name"},
            headers={**OTHER_HEADERS, "X-Team-Id": team.team_id},
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /api/teams/{team_id}/members — list members
# ---------------------------------------------------------------------------


class TestListMembers:
    async def test_list_members(self, team):
        client = _client()
        resp = client.get(f"/api/teams/{team.team_id}/members", headers=OWNER_HEADERS)
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 2
        ids = {m["telegram_id"] for m in items}
        assert ids == {OWNER_ID, OTHER_ID}

    async def test_list_members_forbidden_for_non_member(self, team):
        client = _client()
        resp = client.get(f"/api/teams/{team.team_id}/members", headers=STRANGER_HEADERS)
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# PATCH /api/teams/{team_id}/members/{member_id}/role — update role (owner)
# ---------------------------------------------------------------------------


class TestUpdateMemberRole:
    async def test_update_role_as_owner(self, team):
        client = _client()
        resp = client.patch(
            f"/api/teams/{team.team_id}/members/{OTHER_ID}/role",
            json={"role": "viewer"},
            headers={**OWNER_HEADERS, "X-Team-Id": team.team_id},
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        # Verify role changed
        members = client.get(
            f"/api/teams/{team.team_id}/members", headers=OWNER_HEADERS,
        ).json()["items"]
        other = [m for m in members if m["telegram_id"] == OTHER_ID][0]
        assert other["role"] == "viewer"

    async def test_update_role_forbidden_for_editor(self, team):
        client = _client()
        resp = client.patch(
            f"/api/teams/{team.team_id}/members/{OWNER_ID}/role",
            json={"role": "viewer"},
            headers={**OTHER_HEADERS, "X-Team-Id": team.team_id},
        )
        assert resp.status_code == 403

    async def test_update_role_nonexistent_member(self, team):
        client = _client()
        resp = client.patch(
            f"/api/teams/{team.team_id}/members/99999/role",
            json={"role": "viewer"},
            headers={**OWNER_HEADERS, "X-Team-Id": team.team_id},
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "member_not_found"


# ---------------------------------------------------------------------------
# DELETE /api/teams/{team_id}/members/{member_id} — remove member (owner)
# ---------------------------------------------------------------------------


class TestRemoveMember:
    async def test_remove_member_as_owner(self, team):
        client = _client()
        resp = client.delete(
            f"/api/teams/{team.team_id}/members/{OTHER_ID}",
            headers={**OWNER_HEADERS, "X-Team-Id": team.team_id},
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        # Verify member removed
        members = client.get(
            f"/api/teams/{team.team_id}/members", headers=OWNER_HEADERS,
        ).json()["items"]
        assert len(members) == 1

    async def test_remove_self_rejected(self, team):
        client = _client()
        resp = client.delete(
            f"/api/teams/{team.team_id}/members/{OWNER_ID}",
            headers={**OWNER_HEADERS, "X-Team-Id": team.team_id},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "cannot_remove_self"

    async def test_remove_member_forbidden_for_editor(self, team):
        client = _client()
        resp = client.delete(
            f"/api/teams/{team.team_id}/members/{OWNER_ID}",
            headers={**OTHER_HEADERS, "X-Team-Id": team.team_id},
        )
        assert resp.status_code == 403

    async def test_remove_nonexistent_member(self, team):
        client = _client()
        resp = client.delete(
            f"/api/teams/{team.team_id}/members/99999",
            headers={**OWNER_HEADERS, "X-Team-Id": team.team_id},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/teams/{team_id}/leave — leave team
# ---------------------------------------------------------------------------


class TestLeaveTeam:
    async def test_editor_can_leave(self, team):
        client = _client()
        resp = client.post(
            f"/api/teams/{team.team_id}/leave",
            headers=OTHER_HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        # Verify they are gone
        members = client.get(
            f"/api/teams/{team.team_id}/members", headers=OWNER_HEADERS,
        ).json()["items"]
        ids = {m["telegram_id"] for m in members}
        assert OTHER_ID not in ids

    async def test_owner_cannot_leave(self, team):
        client = _client()
        resp = client.post(
            f"/api/teams/{team.team_id}/leave",
            headers=OWNER_HEADERS,
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "owner_cannot_leave"

    async def test_stranger_cannot_leave(self, team):
        client = _client()
        resp = client.post(
            f"/api/teams/{team.team_id}/leave",
            headers=STRANGER_HEADERS,
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /api/teams/{team_id}/invites — create invite (owner only)
# ---------------------------------------------------------------------------


class TestCreateInvite:
    async def test_create_invite_as_owner(self, team):
        client = _client()
        resp = client.post(
            f"/api/teams/{team.team_id}/invites",
            json={"role": "editor", "max_uses": 5},
            headers={**OWNER_HEADERS, "X-Team-Id": team.team_id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "invite_code" in data
        assert "deep_link" in data
        assert data["invite_code"]  # non-empty

    async def test_create_invite_default_role(self, team):
        client = _client()
        resp = client.post(
            f"/api/teams/{team.team_id}/invites",
            json={},
            headers={**OWNER_HEADERS, "X-Team-Id": team.team_id},
        )
        assert resp.status_code == 200
        assert resp.json()["invite_code"]

    async def test_create_invite_forbidden_for_editor(self, team):
        client = _client()
        resp = client.post(
            f"/api/teams/{team.team_id}/invites",
            json={"role": "viewer"},
            headers={**OTHER_HEADERS, "X-Team-Id": team.team_id},
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /api/invites/{invite_code}/accept — accept invite
# ---------------------------------------------------------------------------


class TestAcceptInvite:
    async def test_accept_invite_flow(self, team):
        """Full flow: owner creates invite, stranger accepts it."""
        client = _client()

        # Owner creates invite
        create_resp = client.post(
            f"/api/teams/{team.team_id}/invites",
            json={"role": "viewer", "max_uses": 1},
            headers={**OWNER_HEADERS, "X-Team-Id": team.team_id},
        )
        invite_code = create_resp.json()["invite_code"]

        # Stranger accepts invite
        accept_resp = client.post(
            f"/api/invites/{invite_code}/accept",
            headers=STRANGER_HEADERS,
        )
        assert accept_resp.status_code == 200
        data = accept_resp.json()
        assert data["joined"] is True
        assert data["team_id"] == team.team_id
        assert data["role"] == "viewer"

    async def test_accept_invite_already_member(self, team):
        """Accepting invite when already a member returns already_member."""
        client = _client()

        create_resp = client.post(
            f"/api/teams/{team.team_id}/invites",
            json={"role": "viewer", "max_uses": 5},
            headers={**OWNER_HEADERS, "X-Team-Id": team.team_id},
        )
        invite_code = create_resp.json()["invite_code"]

        # OTHER_ID is already a member (editor)
        accept_resp = client.post(
            f"/api/invites/{invite_code}/accept",
            headers=OTHER_HEADERS,
        )
        assert accept_resp.status_code == 200
        assert accept_resp.json()["already_member"] is True

    async def test_accept_invite_exhausted(self, team):
        """Invite with max_uses=1 cannot be used twice."""
        client = _client()

        create_resp = client.post(
            f"/api/teams/{team.team_id}/invites",
            json={"role": "viewer", "max_uses": 1},
            headers={**OWNER_HEADERS, "X-Team-Id": team.team_id},
        )
        invite_code = create_resp.json()["invite_code"]

        # First use
        client.post(f"/api/invites/{invite_code}/accept", headers=STRANGER_HEADERS)

        # Second use — different user
        second_headers = {
            "X-Telegram-Init-Data": 'user=%7B%22id%22%3A88888%2C%22username%22%3A%22second%22%7D&auth_date=9999999999&hash=abc',
        }
        resp = client.post(f"/api/invites/{invite_code}/accept", headers=second_headers)
        assert resp.status_code == 404
        assert resp.json()["detail"] == "invite_not_found_or_expired"

    async def test_accept_nonexistent_invite(self, team):
        client = _client()
        resp = client.post(
            "/api/invites/nonexistent_code_xyz/accept",
            headers=STRANGER_HEADERS,
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "invite_not_found_or_expired"


# ---------------------------------------------------------------------------
# Default domain (GET + PATCH)
# ---------------------------------------------------------------------------


class TestDefaultDomain:
    async def test_get_team_detail_includes_default_domain(self, team):
        client = _client()
        resp = client.get(f"/api/teams/{team.team_id}", headers=OWNER_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert "default_domain" in data
        assert data["default_domain"] == "aroma"  # default value

    async def test_patch_default_domain_as_owner(self, team):
        client = _client()
        resp = client.patch(
            f"/api/teams/{team.team_id}",
            json={"default_domain": "body"},
            headers={**OWNER_HEADERS, "X-Team-Id": team.team_id},
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        # Verify domain persisted
        detail = client.get(f"/api/teams/{team.team_id}", headers=OWNER_HEADERS)
        assert detail.json()["default_domain"] == "body"

    async def test_patch_default_domain_sound(self, team):
        client = _client()
        resp = client.patch(
            f"/api/teams/{team.team_id}",
            json={"default_domain": "sound"},
            headers={**OWNER_HEADERS, "X-Team-Id": team.team_id},
        )
        assert resp.status_code == 200

        detail = client.get(f"/api/teams/{team.team_id}", headers=OWNER_HEADERS)
        assert detail.json()["default_domain"] == "sound"

    async def test_patch_invalid_domain_rejected(self, team):
        client = _client()
        resp = client.patch(
            f"/api/teams/{team.team_id}",
            json={"default_domain": "invalid_domain"},
            headers={**OWNER_HEADERS, "X-Team-Id": team.team_id},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "invalid_domain"

    async def test_patch_domain_forbidden_for_editor(self, team):
        client = _client()
        resp = client.patch(
            f"/api/teams/{team.team_id}",
            json={"default_domain": "body"},
            headers={**OTHER_HEADERS, "X-Team-Id": team.team_id},
        )
        assert resp.status_code == 403

    async def test_patch_domain_only_without_name(self, team):
        """PATCH with only default_domain should not require name."""
        client = _client()
        resp = client.patch(
            f"/api/teams/{team.team_id}",
            json={"default_domain": "sound"},
            headers={**OWNER_HEADERS, "X-Team-Id": team.team_id},
        )
        assert resp.status_code == 200

        # Team name unchanged
        detail = client.get(f"/api/teams/{team.team_id}", headers=OWNER_HEADERS)
        assert detail.json()["name"] == "Test Team"
        assert detail.json()["default_domain"] == "sound"
