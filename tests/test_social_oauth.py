from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx

import pytest

from bot.services.social_oauth import (
    OAuthExchangeError,
    build_oauth_state,
    build_instagram_authorize_url,
    build_threads_authorize_url,
    exchange_instagram_code,
    exchange_threads_code,
    parse_oauth_state,
    refresh_facebook_token,
    update_env_file,
)


def test_build_threads_authorize_url():
    url = build_threads_authorize_url(
        client_id="threads-app-id",
        redirect_uri="https://oauth.aromara.ru/threads/callback",
        state="abc123",
    )
    parsed = urlparse(url)
    query = parse_qs(parsed.query)

    assert parsed.netloc == "www.threads.net"
    assert query["client_id"] == ["threads-app-id"]
    assert query["redirect_uri"] == ["https://oauth.aromara.ru/threads/callback"]
    assert query["response_type"] == ["code"]
    assert query["state"] == ["abc123"]


def test_build_instagram_authorize_url():
    url = build_instagram_authorize_url(
        client_id="instagram-app-id",
        redirect_uri="https://oauth.aromara.ru/instagram/callback",
    )
    parsed = urlparse(url)
    query = parse_qs(parsed.query)

    assert parsed.netloc == "www.instagram.com"
    assert parsed.path == "/oauth/authorize"
    assert query["client_id"] == ["instagram-app-id"]
    assert query["redirect_uri"] == ["https://oauth.aromara.ru/instagram/callback"]
    assert query["response_type"] == ["code"]
    assert query["enable_fb_login"] == ["0"]


def test_oauth_state_roundtrip():
    state = build_oauth_state(
        secret="telegram-secret",
        service="threads",
        chat_id=12345,
        user_id=67890,
    )
    parsed = parse_oauth_state(state=state, secret="telegram-secret")

    assert parsed.service == "threads"
    assert parsed.chat_id == "12345"
    assert parsed.user_id == "67890"


def test_exchange_threads_code_uses_long_lived_token_and_profile_lookup():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/access_token":
            return httpx.Response(200, json={"access_token": "short-token", "token_type": "bearer"})
        if request.url.path == "/access_token":
            assert request.url.params["grant_type"] == "th_exchange_token"
            return httpx.Response(200, json={"access_token": "long-token", "expires_in": 5_184_000})
        if request.url.path == "/me":
            assert request.headers["Authorization"] == "Bearer long-token"
            return httpx.Response(200, json={"id": "12345", "username": "stress_ins", "name": "Stress"})
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    bundle = exchange_threads_code(
        code="sample-code",
        client_id="threads-app-id",
        client_secret="threads-secret",
        redirect_uri="https://oauth.aromara.ru/threads/callback",
        client=client,
    )

    assert bundle.access_token == "long-token"
    assert bundle.short_lived_token == "short-token"
    assert bundle.user_id == "12345"
    assert bundle.username == "stress_ins"


def test_exchange_instagram_code_uses_long_lived_token():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.instagram.com" and request.url.path == "/oauth/access_token":
            return httpx.Response(200, json={"access_token": "ig-short", "user_id": "777"})
        if request.url.host == "graph.instagram.com" and request.url.path == "/access_token":
            assert request.url.params["grant_type"] == "ig_exchange_token"
            return httpx.Response(200, json={"access_token": "ig-long", "expires_in": 5_184_000})
        if request.url.host == "graph.instagram.com" and request.url.path == "/me":
            return httpx.Response(200, json={"user_id": "777", "username": "aromara.ru"})
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    bundle = exchange_instagram_code(
        code="ig-code",
        client_id="instagram-app-id",
        client_secret="instagram-secret",
        redirect_uri="https://oauth.aromara.ru/instagram/callback",
        client=client,
    )

    assert bundle.access_token == "ig-long"
    assert bundle.short_lived_token == "ig-short"
    assert bundle.user_id == "777"
    assert bundle.username == "aromara.ru"


def test_update_env_file_replaces_existing_values(tmp_path: Path):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "THREADS_ACCESS_TOKEN=old",
                "THREADS_USER_ID=old-user",
                "# comment",
                "OTHER=value",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    update_env_file(
        env_path,
        {
            "THREADS_ACCESS_TOKEN": "new-token",
            "THREADS_USER_ID": "new-user",
            "THREADS_USERNAME": "stress_ins",
        },
    )

    content = env_path.read_text(encoding="utf-8")
    assert "THREADS_ACCESS_TOKEN=new-token" in content
    assert "THREADS_USER_ID=new-user" in content
    assert "THREADS_USERNAME=stress_ins" in content
    assert "# comment" in content
    assert "OTHER=value" in content


def test_refresh_facebook_token_success():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "graph.facebook.com"
        assert request.url.params["grant_type"] == "fb_exchange_token"
        assert request.url.params["fb_exchange_token"] == "old-long-token"
        assert request.url.params["client_id"] == "fb-app-id"
        assert request.url.params["client_secret"] == "fb-secret"
        return httpx.Response(200, json={
            "access_token": "new-long-token",
            "token_type": "bearer",
            "expires_in": 5184000,
        })

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = refresh_facebook_token(
        access_token="old-long-token",
        client_id="fb-app-id",
        client_secret="fb-secret",
        client=client,
    )

    assert result["access_token"] == "new-long-token"
    assert result["expires_in"] == 5184000


def test_refresh_facebook_token_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"access_token": ""})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(OAuthExchangeError, match="access_token"):
        refresh_facebook_token(
            access_token="expired",
            client_id="fb-app-id",
            client_secret="fb-secret",
            client=client,
        )
