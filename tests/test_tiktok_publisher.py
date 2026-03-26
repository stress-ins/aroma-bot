"""Tests for TikTok publishing — OAuth, publisher, and router integration."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from bot.services.social_oauth import (
    TIKTOK_AUTHORIZE_URL,
    TIKTOK_DEFAULT_SCOPES,
    OAuthTokenBundle,
    build_tiktok_authorize_url,
    exchange_tiktok_code,
    refresh_tiktok_token,
    OAuthExchangeError,
)


# ---------------------------------------------------------------------------
# OAuth URL building
# ---------------------------------------------------------------------------


def test_build_tiktok_authorize_url():
    url = build_tiktok_authorize_url(
        client_key="test_key",
        redirect_uri="https://example.com/callback",
        state="abc123",
    )
    assert url.startswith(TIKTOK_AUTHORIZE_URL)
    assert "client_key=test_key" in url
    assert "redirect_uri=" in url
    assert "response_type=code" in url
    assert "scope=video.upload" in url
    assert "state=abc123" in url


def test_build_tiktok_authorize_url_no_state():
    url = build_tiktok_authorize_url(
        client_key="key",
        redirect_uri="https://example.com/cb",
    )
    assert "state=" not in url


def test_build_tiktok_authorize_url_custom_scopes():
    url = build_tiktok_authorize_url(
        client_key="key",
        redirect_uri="https://example.com/cb",
        scopes=("video.upload",),
    )
    assert "video.upload" in url
    assert "video.publish" not in url


# ---------------------------------------------------------------------------
# Token exchange (mocked HTTP)
# ---------------------------------------------------------------------------


def test_exchange_tiktok_code_success():
    mock_client = MagicMock(spec=httpx.Client)

    # Token response
    token_resp = MagicMock()
    token_resp.status_code = 200
    token_resp.json.return_value = {
        "access_token": "access_tok_123",
        "refresh_token": "refresh_tok_456",
        "expires_in": 86400,
        "open_id": "user_open_id",
    }

    # User info response
    user_resp = MagicMock()
    user_resp.status_code = 200
    user_resp.json.return_value = {
        "data": {
            "user": {
                "open_id": "user_open_id",
                "display_name": "TestUser",
                "avatar_url": "https://example.com/avatar.jpg",
            }
        }
    }

    mock_client.post.return_value = token_resp
    mock_client.get.return_value = user_resp

    bundle = exchange_tiktok_code(
        code="auth_code",
        client_key="key",
        client_secret="secret",
        redirect_uri="https://example.com/cb",
        client=mock_client,
    )

    assert isinstance(bundle, OAuthTokenBundle)
    assert bundle.service == "tiktok"
    assert bundle.access_token == "access_tok_123"
    assert bundle.user_id == "user_open_id"
    assert bundle.username == "TestUser"
    assert bundle.metadata["refresh_token"] == "refresh_tok_456"


def test_exchange_tiktok_code_no_access_token():
    mock_client = MagicMock(spec=httpx.Client)
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"access_token": "", "open_id": "uid"}
    mock_client.post.return_value = resp

    with pytest.raises(OAuthExchangeError, match="access_token"):
        exchange_tiktok_code(
            code="code",
            client_key="key",
            client_secret="secret",
            redirect_uri="https://example.com/cb",
            client=mock_client,
        )


# ---------------------------------------------------------------------------
# Token refresh (mocked HTTP)
# ---------------------------------------------------------------------------


def test_refresh_tiktok_token_success():
    mock_client = MagicMock(spec=httpx.Client)
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "access_token": "new_access",
        "refresh_token": "new_refresh",
        "expires_in": 86400,
    }
    mock_client.post.return_value = resp

    result = refresh_tiktok_token(
        refresh_token="old_refresh",
        client_key="key",
        client_secret="secret",
        client=mock_client,
    )

    assert result["access_token"] == "new_access"
    assert result["refresh_token"] == "new_refresh"
    assert result["expires_in"] == 86400


def test_refresh_tiktok_token_failure():
    mock_client = MagicMock(spec=httpx.Client)
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"access_token": ""}
    mock_client.post.return_value = resp

    with pytest.raises(OAuthExchangeError, match="access_token"):
        refresh_tiktok_token(
            refresh_token="old",
            client_key="key",
            client_secret="secret",
            client=mock_client,
        )


# ---------------------------------------------------------------------------
# TikTok publisher (mocked HTTP)
# ---------------------------------------------------------------------------


async def test_publish_to_tiktok_success():
    from bot.services.tiktok_publisher import publish_to_tiktok

    mock_token = MagicMock()
    mock_token.access_token = "tok_123"

    init_resp = httpx.Response(
        200,
        json={
            "data": {"publish_id": "pub_001"},
            "error": {"code": "ok", "message": ""},
        },
    )
    status_resp = httpx.Response(
        200,
        json={
            "data": {"status": "PUBLISH_COMPLETE"},
            "error": {"code": "ok", "message": ""},
        },
    )

    async def mock_post(url, **kwargs):
        if "init" in url:
            return init_resp
        return status_resp

    with (
        patch("bot.services.tiktok_publisher._get_tiktok_token", new_callable=AsyncMock, return_value="tok_123"),
        patch("httpx.AsyncClient.post", side_effect=mock_post),
    ):
        result = await publish_to_tiktok("Test caption", "https://example.com/video.mp4")

    assert result["publish_id"] == "pub_001"
    assert result["status"] == "PUBLISH_COMPLETE"


async def test_publish_to_tiktok_no_token():
    from bot.services.tiktok_publisher import publish_to_tiktok

    with patch(
        "bot.services.tiktok_publisher._get_tiktok_token",
        new_callable=AsyncMock,
        side_effect=RuntimeError("tiktok_token_not_configured"),
    ):
        with pytest.raises(RuntimeError, match="tiktok_token_not_configured"):
            await publish_to_tiktok("Caption", "https://example.com/video.mp4")


async def test_publish_to_tiktok_api_error():
    from bot.services.tiktok_publisher import publish_to_tiktok

    error_resp = httpx.Response(
        401,
        json={"error": {"code": "invalid_token", "message": "Token expired"}},
    )

    with (
        patch("bot.services.tiktok_publisher._get_tiktok_token", new_callable=AsyncMock, return_value="tok_123"),
        patch("httpx.AsyncClient.post", return_value=error_resp),
    ):
        with pytest.raises(RuntimeError, match="Token expired"):
            await publish_to_tiktok("Caption", "https://example.com/video.mp4")


# ---------------------------------------------------------------------------
# Publisher facade routing
# ---------------------------------------------------------------------------


async def test_publisher_routes_tiktok():
    """TikTok platform should route through _tiktok_publish."""
    from bot.services.drafts_store import DraftRecord
    from bot.services.publisher import publish

    draft = DraftRecord(
        draft_id="d_tt",
        kind="tiktok",
        topic="Test TikTok",
        source="test",
        created_at=datetime.now(timezone.utc).isoformat(),
        status="approved",
        feedback="",
        payload={
            "text": "TikTok post",
            "video": {"public_url": "https://example.com/video.mp4"},
        },
    )

    mock_tiktok_result = {"publish_id": "pub_tt", "status": "PUBLISH_COMPLETE"}

    with (
        patch("bot.services.publisher.get_draft", new_callable=AsyncMock, return_value=draft),
        patch("bot.services.publisher.update_draft", new_callable=AsyncMock, return_value=draft),
        patch("bot.services.tiktok_publisher.publish_to_tiktok", new_callable=AsyncMock, return_value=mock_tiktok_result),
    ):
        results = await publish("d_tt", ["tiktok"])

    assert "tiktok" in results
    assert results["tiktok"]["status"] == "success"
    assert results["tiktok"]["external_id"] == "pub_tt"


async def test_publisher_tiktok_requires_video():
    """TikTok should fail gracefully when no video is present."""
    from bot.services.drafts_store import DraftRecord
    from bot.services.publisher import publish

    draft = DraftRecord(
        draft_id="d_tt_novid",
        kind="threads",
        topic="No video",
        source="test",
        created_at=datetime.now(timezone.utc).isoformat(),
        status="approved",
        feedback="",
        payload={"text": "Just text, no video"},
    )

    with (
        patch("bot.services.publisher.get_draft", new_callable=AsyncMock, return_value=draft),
        patch("bot.services.publisher.update_draft", new_callable=AsyncMock, return_value=draft),
    ):
        results = await publish("d_tt_novid", ["tiktok"])

    assert results["tiktok"]["status"] == "failed"
    assert "video" in results["tiktok"]["error"].lower()


# ---------------------------------------------------------------------------
# Publish router validation
# ---------------------------------------------------------------------------


async def test_publish_router_accepts_tiktok():
    """The publish router should accept 'tiktok' as a valid platform."""
    from bot.services.drafts_store import DraftRecord

    draft = DraftRecord(
        draft_id="d_rt",
        kind="tiktok",
        topic="Router test",
        source="test",
        created_at=datetime.now(timezone.utc).isoformat(),
        status="approved",
        feedback="",
        payload={
            "text": "Router TikTok",
            "video": {"public_url": "https://example.com/v.mp4"},
        },
    )

    mock_result = {"tiktok": {"status": "success", "external_id": "pub_123"}}

    with (
        patch("miniapp.api.routers.publish.get_draft", new_callable=AsyncMock, return_value=draft),
        patch("miniapp.api.routers.publish.publish", new_callable=AsyncMock, return_value=mock_result),
    ):
        from miniapp.api.routers.publish import publish_draft, PublishPayload
        payload = PublishPayload(platforms=["tiktok"])
        resp = await publish_draft("d_rt", payload)
        assert resp["results"]["tiktok"]["status"] == "success"


async def test_publish_router_tiktok_requires_video():
    """TikTok should be rejected at router level if draft has no video."""
    from bot.services.drafts_store import DraftRecord
    from fastapi import HTTPException

    draft = DraftRecord(
        draft_id="d_rt_nv",
        kind="threads",
        topic="No vid",
        source="test",
        created_at=datetime.now(timezone.utc).isoformat(),
        status="approved",
        feedback="",
        payload={"text": "No video here"},
    )

    with patch("miniapp.api.routers.publish.get_draft", new_callable=AsyncMock, return_value=draft):
        from miniapp.api.routers.publish import publish_draft, PublishPayload
        payload = PublishPayload(platforms=["tiktok"])
        with pytest.raises(HTTPException) as exc_info:
            await publish_draft("d_rt_nv", payload)
        assert exc_info.value.status_code == 400
        assert "tiktok_requires_video" in exc_info.value.detail


# ---------------------------------------------------------------------------
# Video status check
# ---------------------------------------------------------------------------


async def test_get_tiktok_video_status():
    from bot.services.tiktok_publisher import get_tiktok_video_status

    status_resp = httpx.Response(
        200,
        json={
            "data": {"status": "PUBLISH_COMPLETE", "publish_id": "pub_001"},
            "error": {"code": "ok", "message": ""},
        },
    )

    with (
        patch("bot.services.tiktok_publisher._get_tiktok_token", new_callable=AsyncMock, return_value="tok_123"),
        patch("httpx.AsyncClient.post", return_value=status_resp),
    ):
        result = await get_tiktok_video_status("pub_001")

    assert result["status"] == "PUBLISH_COMPLETE"
