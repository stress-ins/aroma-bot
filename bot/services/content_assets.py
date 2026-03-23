"""Save and serve photo assets for content drafts (stock, upload, AI)."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

CONTENT_ASSETS_DIR = Path(
    os.getenv(
        "AROMA_CONTENT_ASSETS_DIR",
        Path(__file__).parent.parent.parent / "data" / "content_assets",
    )
)
CONTENT_ASSETS_DIR.mkdir(parents=True, exist_ok=True)

# Mapping of PIL format → file extension
_EXT_MAP = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}


def save_content_photo(
    draft_id: str,
    image_bytes: bytes,
    *,
    source: str = "upload",
    photographer: str = "",
    photographer_url: str = "",
    attribution: str = "",
    ext: str = ".jpg",
) -> dict[str, str]:
    """Save photo to disk, return metadata dict for draft payload."""
    directory = CONTENT_ASSETS_DIR / draft_id
    directory.mkdir(parents=True, exist_ok=True)

    filename = f"photo_{uuid4().hex[:8]}{ext}"
    (directory / filename).write_bytes(image_bytes)

    return {
        "filename": filename,
        "url": f"/generated/content_assets/{draft_id}/{filename}",
        "source": source,
        "photographer": photographer,
        "photographer_url": photographer_url,
        "attribution": attribution,
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }


def ext_for_format(fmt: str) -> str:
    """Return file extension for a PIL image format string."""
    return _EXT_MAP.get(fmt.upper(), ".jpg")
