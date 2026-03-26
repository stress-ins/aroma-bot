"""Canva Connect API — import/export designs as PPTX."""
from __future__ import annotations

import asyncio
import base64
import json as _json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from bot.services.mentions_store import get_token, upsert_token
from config import settings

logger = logging.getLogger(__name__)

CANVA_API_BASE = "https://api.canva.com/rest/v1"
POLL_INTERVAL = 3
POLL_TIMEOUT = 600  # 10 minutes — large carousels can take a while

UPLOAD_TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=60.0, pool=10.0)
POLL_TIMEOUT_CFG = httpx.Timeout(connect=10.0, read=15.0, write=10.0, pool=10.0)
DOWNLOAD_TIMEOUT = httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=10.0)
LIST_TIMEOUT = httpx.Timeout(connect=10.0, read=15.0, write=10.0, pool=10.0)


class CanvaAPIError(RuntimeError):
    pass


async def _try_refresh_canva_token(token_record) -> str | None:
    """Attempt to refresh the Canva access token. Returns new access_token or None."""
    if not token_record or not token_record.refresh_token:
        return None
    if not settings.canva_client_id or not settings.canva_client_secret:
        return None
    try:
        from bot.services.social_oauth import refresh_canva_token
        result = refresh_canva_token(
            refresh_token=token_record.refresh_token,
            client_id=settings.canva_client_id,
            client_secret=settings.canva_client_secret,
        )
        expires_at = None
        if result.get("expires_in"):
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(result["expires_in"]))
        await upsert_token(
            platform="canva",
            access_token=str(result["access_token"]),
            expires_at=expires_at,
            refresh_token=str(result.get("refresh_token", "")),
        )
        logger.info("Canva token refreshed successfully")
        return str(result["access_token"])
    except Exception:
        logger.exception("Canva token refresh failed")
        return None


async def _get_canva_token() -> str:
    token = await get_token("canva")
    if not token or not token.access_token:
        raise CanvaAPIError("Canva не подключён. Подключите в Настройки → Аккаунты.")
    # Auto-refresh if expired
    if token.expires_at:
        exp = token.expires_at if token.expires_at.tzinfo else token.expires_at.replace(tzinfo=timezone.utc)
        if exp <= datetime.now(timezone.utc):
            new_token = await _try_refresh_canva_token(token)
            if new_token:
                return new_token
            raise CanvaAPIError("Токен Canva истёк. Переподключите Canva в Настройки → Аккаунты.")
    return token.access_token


async def _request_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    access_token: str,
    **kwargs: Any,
) -> httpx.Response:
    """Make a Canva API request; on 401, try refresh once and retry."""
    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {access_token}"
    resp = await client.request(method, url, headers=headers, **kwargs)
    if resp.status_code != 401:
        return resp
    # Try refresh
    token_record = await get_token("canva")
    new_token = await _try_refresh_canva_token(token_record)
    if not new_token:
        raise CanvaAPIError("Токен Canva истёк. Переподключите Canva в Настройки → Аккаунты.")
    headers["Authorization"] = f"Bearer {new_token}"
    return await client.request(method, url, headers=headers, **kwargs)


async def export_to_canva(pptx_bytes: bytes, title: str) -> dict[str, str]:
    """Upload PPTX to Canva as a new design. Returns {design_id, edit_url}."""
    access_token = await _get_canva_token()

    async with httpx.AsyncClient(timeout=UPLOAD_TIMEOUT) as client:
        # Start import job — Canva expects octet-stream + Import-Metadata header
        title_b64 = base64.b64encode(title[:50].encode()).decode()
        import_metadata = _json.dumps({
            "title_base64": title_b64,
            "mime_type": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        })
        resp = await _request_with_retry(
            client, "POST", f"{CANVA_API_BASE}/imports",
            access_token,
            headers={"Content-Type": "application/octet-stream", "Import-Metadata": import_metadata},
            content=pptx_bytes,
        )
        if resp.status_code >= 400:
            logger.error("Canva import failed: %s %s", resp.status_code, resp.text[:200])
            raise CanvaAPIError(f"Canva import failed: {resp.status_code} {resp.text[:200]}")
        job = resp.json()
        job_id = job.get("job", {}).get("id") or job.get("id", "")
        if not job_id:
            raise CanvaAPIError(f"Canva import did not return job id: {job}")

        # Poll until done — use token from the response Authorization header (may be refreshed)
        poll_token = resp.request.headers.get("Authorization", "").removeprefix("Bearer ") or access_token

    # Poll in separate client to avoid sharing session timeout
    result = await _poll_job(poll_token, f"{CANVA_API_BASE}/imports/{job_id}")

    design_id = result.get("design", {}).get("id", "")
    edit_url = result.get("design", {}).get("urls", {}).get("edit_url", "")
    return {"design_id": design_id, "edit_url": edit_url}


async def export_canva_design(design_id: str) -> bytes:
    """Export a Canva design as PPTX bytes."""
    access_token = await _get_canva_token()

    async with httpx.AsyncClient(timeout=UPLOAD_TIMEOUT) as client:
        resp = await _request_with_retry(
            client, "POST", f"{CANVA_API_BASE}/exports",
            access_token,
            headers={"Content-Type": "application/json"},
            json={"design_id": design_id, "format": {"type": "pptx"}},
        )
        if resp.status_code >= 400:
            logger.error("Canva export failed: %s %s", resp.status_code, resp.text[:200])
            raise CanvaAPIError(f"Canva export failed: {resp.status_code} {resp.text[:200]}")
        job = resp.json()
        job_id = job.get("job", {}).get("id") or job.get("id", "")
        if not job_id:
            raise CanvaAPIError(f"Canva export did not return job id: {job}")

        poll_token = resp.request.headers.get("Authorization", "").removeprefix("Bearer ") or access_token

    # Poll in separate client to avoid sharing session timeout
    result = await _poll_job(poll_token, f"{CANVA_API_BASE}/exports/{job_id}")

    download_url = ""
    urls = result.get("urls", [])
    if isinstance(urls, list) and urls:
        download_url = urls[0]
    elif isinstance(urls, dict):
        download_url = urls.get("url", "")

    if not download_url:
        raise CanvaAPIError("Canva export completed but no download URL returned")

    async with httpx.AsyncClient(timeout=DOWNLOAD_TIMEOUT) as client:
        dl_resp = await client.get(download_url)
        if dl_resp.status_code >= 400:
            logger.error("Failed to download exported file: %s", dl_resp.status_code)
            raise CanvaAPIError(f"Failed to download exported file: {dl_resp.status_code}")
        return dl_resp.content


async def list_canva_designs(limit: int = 20) -> list[dict[str, Any]]:
    """List recent Canva designs."""
    access_token = await _get_canva_token()

    async with httpx.AsyncClient(timeout=LIST_TIMEOUT) as client:
        resp = await _request_with_retry(
            client, "GET", f"{CANVA_API_BASE}/designs",
            access_token,
            params={"limit": min(limit, 50)},
        )
        if resp.status_code >= 400:
            logger.error("Canva list designs failed: %s %s", resp.status_code, resp.text[:200])
            raise CanvaAPIError(f"Canva list designs failed: {resp.status_code} {resp.text[:200]}")
        data = resp.json()

    items = data.get("items", [])
    return [
        {
            "design_id": item.get("id", ""),
            "title": item.get("title", ""),
            "thumbnail_url": item.get("thumbnail", {}).get("url", "") if isinstance(item.get("thumbnail"), dict) else "",
        }
        for item in items
    ]


async def _poll_job(access_token: str, url: str) -> dict[str, Any]:
    """Poll a Canva async job until completion. Creates its own client per request."""
    start = time.monotonic()
    while True:
        elapsed = time.monotonic() - start
        if elapsed > POLL_TIMEOUT:
            raise CanvaAPIError(f"Загрузка в Canva не завершилась за {POLL_TIMEOUT // 60} мин. Попробуйте ещё раз.")

        await asyncio.sleep(POLL_INTERVAL)
        async with httpx.AsyncClient(timeout=POLL_TIMEOUT_CFG) as client:
            resp = await client.get(url, headers={"Authorization": f"Bearer {access_token}"})
        if resp.status_code >= 500:
            # Canva server error — retry silently (transient)
            logger.warning("Canva poll got %d, retrying...", resp.status_code)
            continue
        if resp.status_code >= 400:
            logger.error("Canva job poll failed: %s %s", resp.status_code, resp.text[:200])
            raise CanvaAPIError(f"Canva job poll failed: {resp.status_code} {resp.text[:200]}")

        data = resp.json()
        job = data.get("job", data)
        status = job.get("status", "")

        if status == "completed":
            return job
        if status in ("failed", "error"):
            error_msg = job.get("error", {}).get("message", "Unknown error") if isinstance(job.get("error"), dict) else str(job.get("error", "Unknown error"))
            logger.error("Canva job failed: %s", error_msg)
            raise CanvaAPIError(f"Canva job failed: {error_msg}")
