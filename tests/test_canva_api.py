from __future__ import annotations

from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from bot.services.canva_api import (
    CanvaAPIError,
    export_to_canva,
    export_canva_design,
    list_canva_designs,
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

    with patch("bot.services.canva_api.POLL_TIMEOUT", 0.1), \
         patch("bot.services.canva_api.POLL_INTERVAL", 0.05):
        with pytest.raises(CanvaAPIError, match="timed out"):
            await _poll_job(client, "token", "https://api.canva.com/rest/v1/imports/j1")

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

    with patch("bot.services.canva_api.POLL_INTERVAL", 0.01):
        with pytest.raises(CanvaAPIError, match="Invalid file format"):
            await _poll_job(client, "token", "https://api.canva.com/rest/v1/exports/j2")

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
