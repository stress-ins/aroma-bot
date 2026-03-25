"""Stock photo search across Unsplash and Pexels APIs."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict, dataclass

import httpx


logger = logging.getLogger(__name__)

log = logging.getLogger(__name__)

_UNSPLASH_BASE = "https://api.unsplash.com"
_PEXELS_BASE = "https://api.pexels.com/v1"
_TIMEOUT = 10.0


@dataclass
class StockPhoto:
    id: str
    source: str  # "unsplash" | "pexels"
    url_thumb: str
    url_regular: str
    url_full: str
    width: int
    height: int
    photographer: str
    photographer_url: str
    attribution: str
    alt_text: str

    def to_dict(self) -> dict:
        return asdict(self)


async def search_stock_photos(
    keywords: list[str],
    *,
    per_source: int = 5,
    orientation: str = "portrait",
    unsplash_key: str = "",
    pexels_key: str = "",
    _client: httpx.AsyncClient | None = None,
) -> list[StockPhoto]:
    """Search Unsplash + Pexels in parallel, interleave results, cap at 9."""
    if not keywords:
        return []

    query = " ".join(keywords[:4])

    async def _run(client: httpx.AsyncClient) -> list[StockPhoto]:
        tasks: list[asyncio.Task] = []
        if unsplash_key:
            tasks.append(asyncio.create_task(
                _search_unsplash(client, query, per_source, orientation, unsplash_key),
            ))
        if pexels_key:
            tasks.append(asyncio.create_task(
                _search_pexels(client, query, per_source, orientation, pexels_key),
            ))
        if not tasks:
            log.warning("stock_photos: no API keys configured")
            return []

        results = await asyncio.gather(*tasks, return_exceptions=True)
        all_photos: list[list[StockPhoto]] = []
        for r in results:
            if isinstance(r, BaseException):
                log.warning("stock_photos: API error: %s", r)
                continue
            all_photos.append(r)
        return _interleave(all_photos, max_total=9)

    if _client is not None:
        return await _run(_client)

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        return await _run(client)


async def download_stock_photo(
    url: str,
    *,
    source: str = "",
    unsplash_key: str = "",
    download_location: str = "",
) -> bytes:
    """Download a stock photo. Triggers Unsplash download tracking (TOS)."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Unsplash TOS: trigger download endpoint
        if source == "unsplash" and download_location and unsplash_key:
            try:
                await client.get(
                    download_location,
                    params={"client_id": unsplash_key},
                )
            except Exception:
                logger.warning("download_stock_photo: client failed", exc_info=True)
                pass  # best-effort tracking

        resp = await client.get(url)
        resp.raise_for_status()
        return resp.content


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

async def _search_unsplash(
    client: httpx.AsyncClient,
    query: str,
    per_page: int,
    orientation: str,
    access_key: str,
) -> list[StockPhoto]:
    resp = await client.get(
        f"{_UNSPLASH_BASE}/search/photos",
        params={
            "query": query,
            "per_page": per_page,
            "orientation": orientation,
            "content_filter": "high",
        },
        headers={"Authorization": f"Client-ID {access_key}"},
    )
    resp.raise_for_status()
    data = resp.json()

    photos: list[StockPhoto] = []
    for item in data.get("results", []):
        urls = item.get("urls", {})
        user = item.get("user", {})
        photos.append(StockPhoto(
            id=item["id"],
            source="unsplash",
            url_thumb=urls.get("thumb", ""),
            url_regular=urls.get("regular", ""),
            url_full=urls.get("full", ""),
            width=item.get("width", 0),
            height=item.get("height", 0),
            photographer=user.get("name", ""),
            photographer_url=user.get("links", {}).get("html", ""),
            attribution=f"Photo by {user.get('name', '')} on Unsplash",
            alt_text=item.get("alt_description", "") or item.get("description", "") or "",
        ))
    return photos


async def _search_pexels(
    client: httpx.AsyncClient,
    query: str,
    per_page: int,
    orientation: str,
    api_key: str,
) -> list[StockPhoto]:
    resp = await client.get(
        f"{_PEXELS_BASE}/search",
        params={
            "query": query,
            "per_page": per_page,
            "orientation": orientation,
        },
        headers={"Authorization": api_key},
    )
    resp.raise_for_status()
    data = resp.json()

    photos: list[StockPhoto] = []
    for item in data.get("photos", []):
        src = item.get("src", {})
        photos.append(StockPhoto(
            id=str(item["id"]),
            source="pexels",
            url_thumb=src.get("small", ""),
            url_regular=src.get("large", ""),
            url_full=src.get("original", ""),
            width=item.get("width", 0),
            height=item.get("height", 0),
            photographer=item.get("photographer", ""),
            photographer_url=item.get("photographer_url", ""),
            attribution=f"Photo by {item.get('photographer', '')} on Pexels",
            alt_text=item.get("alt", "") or "",
        ))
    return photos


def _interleave(lists: list[list[StockPhoto]], max_total: int = 9) -> list[StockPhoto]:
    """Interleave results from multiple sources for variety."""
    result: list[StockPhoto] = []
    seen_ids: set[str] = set()
    max_idx = max((len(lst) for lst in lists), default=0)

    for i in range(max_idx):
        for lst in lists:
            if i < len(lst):
                photo = lst[i]
                key = f"{photo.source}:{photo.id}"
                if key not in seen_ids:
                    seen_ids.add(key)
                    result.append(photo)
                    if len(result) >= max_total:
                        return result
    return result
