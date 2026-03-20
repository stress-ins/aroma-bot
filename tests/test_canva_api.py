from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from bot.services.canva_api import (
    CanvaAPIError,
    export_to_canva,
    export_canva_design,
    list_canva_designs,
    _get_canva_token,
    _try_refresh_canva_token,
    _poll_job,
)


@pytest.fixture
def mock_canva_token():
    """Patch _get_canva_token to return a fake token."""
    with patch("bot.services.canva_api._get_canva_token", new_callable=AsyncMock, return_value="fake-canva-token"):
        yield


@pytest.mark.asyncio
async def test_export_to_canva_success(mock_canva_token):
    """Test that export_to_canva uploads PPTX and returns design info."""
    import httpx

    async def mock_handler(request):
        if request.method == "POST" and "/imports" in str(request.url):
            assert request.headers["Content-Type"] == "application/octet-stream"
            assert "Import-Metadata" in request.headers
            assert request.content == b"fake-pptx-bytes"
            return httpx.Response(200, json={"job": {"id": "job-123", "status": "in_progress"}})
        if request.method == "GET" and "/imports/job-123" in str(request.url):
            return httpx.Response(200, json={
                "job": {
                    "id": "job-123",
                    "status": "completed",
                    "design": {
                        "id": "design-abc",
                        "urls": {"edit_url": "https://canva.com/design/abc/edit"},
                    },
                },
            })
        return httpx.Response(404)

    transport = httpx.MockTransport(mock_handler)

    with patch("bot.services.canva_api.httpx") as mock_httpx:
        mock_client = httpx.AsyncClient(transport=transport)
        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=mock_client)
        ctx.__aexit__ = AsyncMock(return_value=False)
        mock_httpx.AsyncClient.return_value = ctx

        with patch("bot.services.canva_api.POLL_INTERVAL", 0.01):
            result = await export_to_canva(b"fake-pptx-bytes", "Test Carousel")

        await mock_client.aclose()

    assert result["design_id"] == "design-abc"
    assert result["edit_url"] == "https://canva.com/design/abc/edit"


@pytest.mark.asyncio
async def test_list_canva_designs(mock_canva_token):
    """Test listing Canva designs."""
    import httpx

    async def mock_handler(request):
        if "/designs" in str(request.url):
            return httpx.Response(200, json={
                "items": [
                    {"id": "d1", "title": "Design 1", "thumbnail": {"url": "https://example.com/thumb1.png"}},
                    {"id": "d2", "title": "Design 2", "thumbnail": {"url": "https://example.com/thumb2.png"}},
                ]
            })
        return httpx.Response(404)

    transport = httpx.MockTransport(mock_handler)

    with patch("bot.services.canva_api.httpx") as mock_httpx:
        mock_client = httpx.AsyncClient(transport=transport)
        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=mock_client)
        ctx.__aexit__ = AsyncMock(return_value=False)
        mock_httpx.AsyncClient.return_value = ctx

        designs = await list_canva_designs(limit=10)

        await mock_client.aclose()

    assert len(designs) == 2
    assert designs[0]["design_id"] == "d1"
    assert designs[0]["title"] == "Design 1"
    assert designs[1]["thumbnail_url"] == "https://example.com/thumb2.png"


@pytest.mark.asyncio
async def test_get_canva_token_raises_when_not_connected():
    """Test that operations fail gracefully when Canva is not connected."""
    with patch("bot.services.canva_api.get_token", new_callable=AsyncMock, return_value=None):
        with pytest.raises(CanvaAPIError, match="не подключён"):
            await export_to_canva(b"data", "title")


@pytest.mark.asyncio
async def test_poll_job_timeout():
    """Test that polling times out correctly."""
    import httpx

    async def mock_handler(request):
        return httpx.Response(200, json={"job": {"status": "in_progress"}})

    transport = httpx.MockTransport(mock_handler)
    client = httpx.AsyncClient(transport=transport)

    with patch("bot.services.canva_api.httpx") as mock_httpx, \
         patch("bot.services.canva_api.POLL_TIMEOUT", 0.1), \
         patch("bot.services.canva_api.POLL_INTERVAL", 0.05):
        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=client)
        ctx.__aexit__ = AsyncMock(return_value=False)
        mock_httpx.AsyncClient.return_value = ctx
        with pytest.raises(CanvaAPIError, match="timed out"):
            await _poll_job("token", "https://api.canva.com/rest/v1/imports/j1")

    await client.aclose()


@pytest.mark.asyncio
async def test_poll_job_failed():
    """Test that failed job raises error."""
    import httpx

    async def mock_handler(request):
        return httpx.Response(200, json={
            "job": {"status": "failed", "error": {"message": "Invalid file format"}},
        })

    transport = httpx.MockTransport(mock_handler)
    client = httpx.AsyncClient(transport=transport)

    with patch("bot.services.canva_api.httpx") as mock_httpx, \
         patch("bot.services.canva_api.POLL_INTERVAL", 0.01):
        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=client)
        ctx.__aexit__ = AsyncMock(return_value=False)
        mock_httpx.AsyncClient.return_value = ctx
        with pytest.raises(CanvaAPIError, match="Invalid file format"):
            await _poll_job("token", "https://api.canva.com/rest/v1/exports/j2")

    await client.aclose()


@pytest.mark.asyncio
async def test_export_canva_design_success(mock_canva_token):
    """Test exporting a Canva design as PPTX."""
    import httpx

    async def mock_handler(request):
        if request.method == "POST" and "/exports" in str(request.url):
            return httpx.Response(200, json={"job": {"id": "exp-1", "status": "in_progress"}})
        if request.method == "GET" and "/exports/exp-1" in str(request.url):
            return httpx.Response(200, json={
                "job": {
                    "status": "completed",
                    "urls": ["https://dl.canva.com/export.pptx"],
                },
            })
        if "dl.canva.com" in str(request.url):
            return httpx.Response(200, content=b"pptx-file-content")
        return httpx.Response(404)

    transport = httpx.MockTransport(mock_handler)

    with patch("bot.services.canva_api.httpx") as mock_httpx:
        mock_client = httpx.AsyncClient(transport=transport)
        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=mock_client)
        ctx.__aexit__ = AsyncMock(return_value=False)
        mock_httpx.AsyncClient.return_value = ctx

        with patch("bot.services.canva_api.POLL_INTERVAL", 0.01):
            result = await export_canva_design("design-xyz")

        await mock_client.aclose()

    assert result == b"pptx-file-content"


@pytest.mark.asyncio
async def test_get_canva_token_auto_refreshes_when_expired():
    """When access_token is expired and refresh_token is available, auto-refresh kicks in."""
    expired_token = MagicMock()
    expired_token.access_token = "old-token"
    expired_token.refresh_token = "canva-refresh-tok"
    expired_token.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)

    with patch("bot.services.canva_api.get_token", new_callable=AsyncMock, return_value=expired_token), \
         patch("bot.services.canva_api._try_refresh_canva_token", new_callable=AsyncMock, return_value="new-fresh-token"):
        token = await _get_canva_token()
    assert token == "new-fresh-token"


@pytest.mark.asyncio
async def test_get_canva_token_expired_no_refresh_raises():
    """When token expired and refresh fails, raise a clear error."""
    expired_token = MagicMock()
    expired_token.access_token = "old-token"
    expired_token.refresh_token = ""
    expired_token.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)

    with patch("bot.services.canva_api.get_token", new_callable=AsyncMock, return_value=expired_token), \
         patch("bot.services.canva_api._try_refresh_canva_token", new_callable=AsyncMock, return_value=None):
        with pytest.raises(CanvaAPIError, match="истёк"):
            await _get_canva_token()


@pytest.mark.asyncio
async def test_try_refresh_canva_token_success():
    """_try_refresh_canva_token calls refresh_canva_token and persists result."""
    token_record = MagicMock()
    token_record.refresh_token = "rt-123"

    refresh_result = {"access_token": "new-at", "refresh_token": "new-rt", "expires_in": 14400}

    with patch("bot.services.canva_api.settings") as mock_settings, \
         patch("bot.services.social_oauth.refresh_canva_token", return_value=refresh_result) as mock_refresh, \
         patch("bot.services.canva_api.upsert_token", new_callable=AsyncMock) as mock_upsert:
        mock_settings.canva_client_id = "cid"
        mock_settings.canva_client_secret = "csec"

        result = await _try_refresh_canva_token(token_record)

    assert result == "new-at"
    mock_refresh.assert_called_once_with(refresh_token="rt-123", client_id="cid", client_secret="csec")
    mock_upsert.assert_called_once()
    call_kwargs = mock_upsert.call_args
    assert call_kwargs.kwargs["refresh_token"] == "new-rt"


def test_refresh_canva_token_function():
    """Test refresh_canva_token from social_oauth."""
    import httpx
    from bot.services.social_oauth import refresh_canva_token

    def handler(request: httpx.Request) -> httpx.Response:
        assert "oauth/token" in str(request.url)
        assert request.headers.get("Authorization", "").startswith("Basic ")
        body = request.content.decode()
        assert "grant_type=refresh_token" in body
        assert "refresh_token=old-rt" in body
        return httpx.Response(200, json={
            "access_token": "new-access",
            "refresh_token": "new-refresh",
            "expires_in": 14400,
        })

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = refresh_canva_token(
        refresh_token="old-rt",
        client_id="cid",
        client_secret="csec",
        client=client,
    )
    assert result["access_token"] == "new-access"
    assert result["refresh_token"] == "new-refresh"
    assert result["expires_in"] == 14400
