"""Canva Connect API — import/export designs as PPTX."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from bot.services.mentions_store import get_token

logger = logging.getLogger(__name__)

CANVA_API_BASE = "https://api.canva.com/rest/v1"
POLL_INTERVAL = 2
POLL_TIMEOUT = 60


class CanvaAPIError(RuntimeError):
    pass


async def _get_canva_token() -> str:
    token = await get_token("canva")
    if not token or not token.access_token:
        raise CanvaAPIError("Canva не подключён. Подключите в Настройки → Аккаунты.")
    return token.access_token


async def export_to_canva(pptx_bytes: bytes, title: str) -> dict[str, str]:
    """Upload PPTX to Canva as a new design. Returns {design_id, edit_url}."""
    access_token = await _get_canva_token()

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Start import job
        resp = await client.post(
            f"{CANVA_API_BASE}/imports",
            headers={"Authorization": f"Bearer {access_token}"},
            files={"file": (f"{title}.pptx", pptx_bytes, "application/vnd.openxmlformats-officedocument.presentationml.presentation")},
            data={"title": title},
        )
        if resp.status_code >= 400:
            raise CanvaAPIError(f"Canva import failed: {resp.status_code} {resp.text[:200]}")
        job = resp.json()
        job_id = job.get("job", {}).get("id") or job.get("id", "")
        if not job_id:
            raise CanvaAPIError(f"Canva import did not return job id: {job}")

        # Poll until done
        result = await _poll_job(client, access_token, f"{CANVA_API_BASE}/imports/{job_id}")

    design_id = result.get("design", {}).get("id", "")
    edit_url = result.get("design", {}).get("urls", {}).get("edit_url", "")
    return {"design_id": design_id, "edit_url": edit_url}


async def export_canva_design(design_id: str) -> bytes:
    """Export a Canva design as PPTX bytes."""
    access_token = await _get_canva_token()

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{CANVA_API_BASE}/exports",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json={"design_id": design_id, "format": {"type": "pptx"}},
        )
        if resp.status_code >= 400:
            raise CanvaAPIError(f"Canva export failed: {resp.status_code} {resp.text[:200]}")
        job = resp.json()
        job_id = job.get("job", {}).get("id") or job.get("id", "")
        if not job_id:
            raise CanvaAPIError(f"Canva export did not return job id: {job}")

        result = await _poll_job(client, access_token, f"{CANVA_API_BASE}/exports/{job_id}")

    download_url = ""
    urls = result.get("urls", [])
    if isinstance(urls, list) and urls:
        download_url = urls[0]
    elif isinstance(urls, dict):
        download_url = urls.get("url", "")

    if not download_url:
        raise CanvaAPIError("Canva export completed but no download URL returned")

    async with httpx.AsyncClient(timeout=60.0) as client:
        dl_resp = await client.get(download_url)
        if dl_resp.status_code >= 400:
            raise CanvaAPIError(f"Failed to download exported file: {dl_resp.status_code}")
        return dl_resp.content


async def list_canva_designs(limit: int = 20) -> list[dict[str, Any]]:
    """List recent Canva designs."""
    access_token = await _get_canva_token()

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            f"{CANVA_API_BASE}/designs",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"limit": min(limit, 50)},
        )
        if resp.status_code >= 400:
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


async def _poll_job(client: httpx.AsyncClient, access_token: str, url: str) -> dict[str, Any]:
    """Poll a Canva async job until completion."""
    start = time.monotonic()
    while True:
        elapsed = time.monotonic() - start
        if elapsed > POLL_TIMEOUT:
            raise CanvaAPIError(f"Canva job timed out after {POLL_TIMEOUT}s")

        await asyncio.sleep(POLL_INTERVAL)
        resp = await client.get(url, headers={"Authorization": f"Bearer {access_token}"})
        if resp.status_code >= 400:
            raise CanvaAPIError(f"Canva job poll failed: {resp.status_code} {resp.text[:200]}")

        data = resp.json()
        job = data.get("job", data)
        status = job.get("status", "")

        if status == "completed":
            return job
        if status in ("failed", "error"):
            error_msg = job.get("error", {}).get("message", "Unknown error") if isinstance(job.get("error"), dict) else str(job.get("error", "Unknown error"))
            raise CanvaAPIError(f"Canva job failed: {error_msg}")
