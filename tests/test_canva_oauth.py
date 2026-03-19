from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import httpx

from bot.services.social_oauth import (
    build_canva_authorize_url,
    exchange_canva_code,
)


def test_build_canva_authorize_url():
    url = build_canva_authorize_url(
        client_id="canva-app-id",
        redirect_uri="https://oauth.aromara.ru/canva/callback",
        state="xyz789",
    )
    parsed = urlparse(url)
    query = parse_qs(parsed.query)

    assert parsed.netloc == "www.canva.com"
    assert parsed.path == "/api/oauth/authorize"
    assert query["client_id"] == ["canva-app-id"]
    assert query["redirect_uri"] == ["https://oauth.aromara.ru/canva/callback"]
    assert query["response_type"] == ["code"]
    assert query["state"] == ["xyz789"]
    assert "design:content:read" in query["scope"][0]


def test_build_canva_authorize_url_custom_scopes():
    url = build_canva_authorize_url(
        client_id="canva-app-id",
        redirect_uri="https://oauth.aromara.ru/canva/callback",
        scopes=("design:content:read",),
    )
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    assert query["scope"] == ["design:content:read"]


def test_exchange_canva_code_returns_bundle():
    def handler(request: httpx.Request) -> httpx.Response:
        if "oauth/token" in str(request.url):
            return httpx.Response(200, json={
                "access_token": "canva-access-token",
                "refresh_token": "canva-refresh-token",
                "expires_in": 14400,
                "token_type": "bearer",
            })
        if "/users/me" in str(request.url):
            assert "Bearer canva-access-token" in request.headers.get("Authorization", "")
            return httpx.Response(200, json={
                "id": "canva-user-123",
                "display_name": "Test Designer",
            })
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    bundle = exchange_canva_code(
        code="canva-auth-code",
        client_id="canva-app-id",
        client_secret="canva-secret",
        redirect_uri="https://oauth.aromara.ru/canva/callback",
        client=client,
    )

    assert bundle.service == "canva"
    assert bundle.access_token == "canva-access-token"
    assert bundle.user_id == "canva-user-123"
    assert bundle.username == "Test Designer"
    assert bundle.metadata["refresh_token"] == "canva-refresh-token"
    assert bundle.expires_in == 14400


def test_exchange_canva_code_uses_basic_auth():
    """Verify that exchange sends client_id/secret as HTTP Basic Auth."""
    captured_auth = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if "oauth/token" in str(request.url):
            captured_auth["header"] = request.headers.get("Authorization", "")
            return httpx.Response(200, json={
                "access_token": "tok",
                "expires_in": 3600,
            })
        if "/users/me" in str(request.url):
            return httpx.Response(200, json={"id": "u1", "display_name": "X"})
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    exchange_canva_code(
        code="code",
        client_id="cid",
        client_secret="csec",
        redirect_uri="https://example.com/callback",
        client=client,
    )
    assert captured_auth["header"].startswith("Basic ")
