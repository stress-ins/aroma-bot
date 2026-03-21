"""Tests for archive API router (miniapp/api/routers/archive.py)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _bypass_auth(monkeypatch):
    monkeypatch.setenv("AROMA_BYPASS_AUTH", "1")


HEADERS = {
    "X-Telegram-Init-Data": "user=%7B%22id%22%3A12345%7D&auth_date=9999999999&hash=abc",
}


@pytest.fixture()
async def team_with_archive(setup_test_db):
    from bot.services.team_store import create_team
    from bot.services.past_publications_store import create_publication
    from datetime import datetime, timezone

    team = await create_team("Archive Test Team", creator_telegram_id=12345)

    p1 = await create_publication(
        platform="threads", topic="Post about lavender", kind="text",
        likes=50, views=500, team_id=team.team_id, created_by=12345,
        published_at=datetime(2026, 3, 10, tzinfo=timezone.utc),
    )
    p2 = await create_publication(
        platform="instagram", topic="Carousel oils", kind="carousel",
        likes=100, views=1200, team_id=team.team_id, created_by=12345,
        published_at=datetime(2026, 3, 15, tzinfo=timezone.utc),
        score_engagement=4, score_brand_fit=3, score_craft=5, score_goal_hit=4,
    )
    return team, [p1, p2]


class TestListArchive:
    async def test_list_returns_items(self, team_with_archive):
        team, pubs = team_with_archive
        from miniapp_server import app
        client = TestClient(app)
        resp = client.get("/api/archive", headers={**HEADERS, "X-Team-Id": team.team_id})
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert len(data["items"]) == 2

    async def test_filter_by_platform(self, team_with_archive):
        team, pubs = team_with_archive
        from miniapp_server import app
        client = TestClient(app)
        resp = client.get("/api/archive?platform=threads", headers={**HEADERS, "X-Team-Id": team.team_id})
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert all(i["platform"] == "threads" for i in items)

    async def test_filter_rated(self, team_with_archive):
        team, pubs = team_with_archive
        from miniapp_server import app
        client = TestClient(app)
        resp = client.get("/api/archive?filter=rated", headers={**HEADERS, "X-Team-Id": team.team_id})
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["score_engagement"] is not None


class TestArchiveDetail:
    async def test_get_by_id(self, team_with_archive):
        team, pubs = team_with_archive
        from miniapp_server import app
        client = TestClient(app)
        resp = client.get(f"/api/archive/{pubs[0].pub_id}", headers=HEADERS)
        assert resp.status_code == 200
        assert resp.json()["pub_id"] == pubs[0].pub_id

    async def test_not_found(self, team_with_archive):
        from miniapp_server import app
        client = TestClient(app)
        resp = client.get("/api/archive/nonexistent", headers=HEADERS)
        assert resp.status_code == 404


class TestCreateArchive:
    async def test_create(self, team_with_archive):
        team, _ = team_with_archive
        from miniapp_server import app
        client = TestClient(app)
        resp = client.post("/api/archive", json={
            "platform": "telegram",
            "topic": "New post",
            "kind": "text",
            "caption": "Test caption",
            "likes": 10,
            "published_at": "2026-03-20T12:00:00+00:00",
        }, headers={**HEADERS, "X-Team-Id": team.team_id})
        assert resp.status_code == 200
        data = resp.json()
        assert data["platform"] == "telegram"
        assert data["topic"] == "New post"
        assert data["likes"] == 10


class TestUpdateArchive:
    async def test_update_scores(self, team_with_archive):
        team, pubs = team_with_archive
        from miniapp_server import app
        client = TestClient(app)
        resp = client.put(f"/api/archive/{pubs[0].pub_id}", json={
            "score_engagement": 5,
            "score_brand_fit": 4,
            "notes": "Great post!",
        }, headers=HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["score_engagement"] == 5
        assert data["notes"] == "Great post!"


class TestDeleteArchive:
    async def test_delete(self, team_with_archive):
        team, pubs = team_with_archive
        from miniapp_server import app
        client = TestClient(app)
        resp = client.delete(f"/api/archive/{pubs[0].pub_id}", headers=HEADERS)
        assert resp.status_code == 200
        # Verify deleted
        resp2 = client.get(f"/api/archive/{pubs[0].pub_id}", headers=HEADERS)
        assert resp2.status_code == 404


class TestArchiveStats:
    async def test_stats(self, team_with_archive):
        team, _ = team_with_archive
        from miniapp_server import app
        client = TestClient(app)
        resp = client.get("/api/archive/stats", headers={**HEADERS, "X-Team-Id": team.team_id})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert data["rated"] >= 1
        assert "avg_score" in data


class TestImportUrl:
    async def test_import_url_empty(self, team_with_archive):
        team, _ = team_with_archive
        from miniapp_server import app
        client = TestClient(app)
        resp = client.post("/api/archive/import-url", json={"url": ""}, headers={**HEADERS, "X-Team-Id": team.team_id})
        assert resp.status_code == 400

    async def test_import_url_unsupported(self, team_with_archive):
        team, _ = team_with_archive
        from miniapp_server import app
        client = TestClient(app)
        resp = client.post("/api/archive/import-url", json={"url": "https://example.com/post"}, headers={**HEADERS, "X-Team-Id": team.team_id})
        assert resp.status_code == 400
