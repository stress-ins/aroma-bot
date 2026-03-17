"""Unified publisher facade — delegates to upload_post_publisher and telegram_publisher.

Existing consumers (scheduler, miniapp router) import from here for backward
compatibility.  New code should import the specific publisher modules directly.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from bot.services.upload_post_publisher import (
    UPLOAD_POST_PLATFORMS,
    publish_item as _upload_post_publish,
    check_status,
    cancel_scheduled,
    _draft_text,
    _resolve_media_paths,
    _get_upload_client,
)
from bot.services.telegram_publisher import (
    publish_item as _telegram_publish,
)
from bot.services.drafts_store import get_draft, update_draft

logger = logging.getLogger(__name__)

# Re-export for backward compatibility
__all__ = [
    "UPLOAD_POST_PLATFORMS",
    "publish",
    "check_status",
    "cancel_scheduled",
    "_draft_text",
    "_resolve_media_paths",
    "_get_upload_client",
]


async def publish(
    draft_id: str,
    platforms: list[str],
    scheduled_at: datetime | None = None,
    *,
    telegram_bot: Any | None = None,
    telegram_chat_id: str | None = None,
) -> dict[str, Any]:
    """Publish or schedule a draft to the given platforms.

    Routes to upload_post_publisher (threads/instagram) and
    telegram_publisher (telegram).

    Returns dict of {platform: {status, external_id/error}}.
    """
    results: dict[str, Any] = {}

    # Pre-publish quality gate: block if quality_score is critically low
    draft = await get_draft(draft_id)
    if draft:
        quality = (draft.payload or {}).get("quality_score", {})
        overall = quality.get("overall", 1.0) if isinstance(quality, dict) else 1.0
        if overall < 0.5:
            logger.error(
                "Refusing to publish draft %s: quality_score=%.2f (threshold 0.5)",
                draft_id, overall,
            )
            await update_draft(draft_id, status="failed", error=f"quality_score {overall:.2f} below 0.5")
            return {"error": f"quality_score {overall:.2f} below threshold"}
        if overall < 0.65:
            logger.warning("Publishing draft %s with low quality_score=%.2f", draft_id, overall)

    upload_platforms = [p for p in platforms if p in UPLOAD_POST_PLATFORMS]
    if upload_platforms:
        result = await _upload_post_publish(draft_id, upload_platforms, scheduled_at)
        results.update(result)

    if "telegram" in platforms and telegram_bot and telegram_chat_id:
        result = await _telegram_publish(draft_id, telegram_bot, telegram_chat_id)
        results["telegram"] = result

    # Update draft metadata (external_ids, status, platforms) for backward compat
    draft = await get_draft(draft_id)
    if draft:
        external_ids = dict(draft.external_ids or {})
        for platform, info in results.items():
            if isinstance(info, dict) and info.get("external_id"):
                external_ids[platform] = info["external_id"]
        new_status = "scheduled" if scheduled_at else "published"
        await update_draft(
            draft_id,
            status=new_status,
            scheduled_at=scheduled_at,
            publish_platforms=platforms,
            external_ids=external_ids,
        )

    return results
