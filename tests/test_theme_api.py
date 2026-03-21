"""Tests for GET/PATCH /api/preferences/theme."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def miniapp_test_client(monkeypatch):
    import miniapp_server
    import miniapp.api.auth as _miniapp_auth
    from config import settings as _cfg

    monkeypatch.setattr(_miniapp_auth, "_verify_init_data", lambda _value: True)
    monkeypatch.setattr(_cfg, "anthropic_api_key", "test-key")

    with TestClient(miniapp_server.app) as client:
        yield client


AUTH_HEADERS = {"X-Telegram-Init-Data": "test"}


def test_get_default_theme(miniapp_test_client):
    r = miniapp_test_client.get("/api/preferences/theme", headers=AUTH_HEADERS)
    assert r.status_code == 200
    assert r.json()["theme"] == "terracotta"


def test_update_theme(miniapp_test_client):
    r = miniapp_test_client.patch(
        "/api/preferences/theme",
        json={"theme": "violet"},
        headers=AUTH_HEADERS,
    )
    assert r.status_code == 200
    assert r.json()["theme"] == "violet"

    # Verify persisted
    r2 = miniapp_test_client.get("/api/preferences/theme", headers=AUTH_HEADERS)
    assert r2.json()["theme"] == "violet"


def test_invalid_theme_rejected(miniapp_test_client):
    r = miniapp_test_client.patch(
        "/api/preferences/theme",
        json={"theme": "pink"},
        headers=AUTH_HEADERS,
    )
    assert r.status_code == 400
