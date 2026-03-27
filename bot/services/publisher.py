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
    "publish_threads_series_slot",
    "check_status",
    "cancel_scheduled",
    "_draft_text",
    "_resolve_media_paths",
    "_get_upload_client",
]


async def publish_threads_series_slot(draft_id: str, slot: str) -> dict[str, Any]:
    """Publish a single slot of a threads_series via Meta Graph API.

    Updates the slot status to 'published' in the payload.
    If all slots are published, marks the whole draft as 'published'.
    """
    from bot.services.meta_publisher import publish_to_threads

    draft = await get_draft(draft_id)
    if not draft:
        raise RuntimeError(f"Draft {draft_id} not found")

    p = dict(draft.payload or {})
    posts = list(p.get("threads_posts", []))

    slot_post = next((post for post in posts if post["slot"] == slot), None)
    if not slot_post:
        raise RuntimeError(f"Slot {slot} not found in draft {draft_id}")

    text = slot_post.get("text", "")
    if not text.strip():
        raise RuntimeError(f"Slot {slot} has no text")

    result = await publish_to_threads(text)
    logger.info(
        "Published threads_series slot %s for draft %s: %s",
        slot, draft_id, result,
    )

    slot_post["status"] = "published"
    slot_post["external_id"] = result.get("id", "")
    p["threads_posts"] = posts

    all_published = all(
        post.get("status") == "published" for post in posts
    )

    if all_published:
        await update_draft(draft_id, payload=p, status="published")
    else:
        await update_draft(draft_id, payload=p)

    return {"status": "ok", "slot": slot, "external_id": result.get("id", "")}


async def _tiktok_publish(draft_id: str) -> dict[str, Any]:
    """Publish a draft to TikTok. Requires video content."""
    from bot.services.tiktok_publisher import publish_to_tiktok
    from bot.services.meta_publisher import _get_public_image_url

    draft = await get_draft(draft_id)
    if not draft:
        return {"status": "failed", "error": "draft_not_found"}

    payload = dict(draft.payload or {})

    # Extract video URL
    video_url = ""
    video_info = payload.get("video") or {}
    if isinstance(video_info, dict):
        video_url = video_info.get("public_url") or video_info.get("url") or ""
    if not video_url:
        video_url = payload.get("video_url", "")

    if not video_url:
        return {"status": "failed", "error": "tiktok_requires_video"}

    caption = _draft_text(payload, draft.kind or "tiktok")

    try:
        result = await publish_to_tiktok(caption, video_url)
        logger.info("Published to TikTok: draft=%s result=%s", draft_id, result)
        return {
            "status": "success",
            "external_id": result.get("publish_id", ""),
        }
    except Exception as exc:
        logger.error("TikTok publish failed for draft %s: %s", draft_id, exc)
        return {"status": "failed", "error": str(exc)}


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

    # Carousel: publish Instagram/Threads via Meta Graph API directly
    remaining_platforms = list(platforms)
    if draft and draft.kind == "carousel":
        from bot.services.meta_publisher import (
            publish_to_instagram,
            publish_to_threads,
            _get_carousel_image_urls,
            _get_public_image_url,
        )
        from bot.services.publish_log_store import save_log, update_log_status

        caption = _draft_text(draft.payload, draft.kind)
        media_paths = _resolve_media_paths(draft.kind, draft_id, draft.payload)

        if "instagram" in remaining_platforms:
            log_id = await save_log(draft_id, "instagram", "publish", "pending")
            try:
                image_urls = _get_carousel_image_urls(draft.payload or {}, draft_id, media_paths)
                if not image_urls:
                    raise RuntimeError("carousel_no_images")
                result = await publish_to_instagram(caption, carousel_image_urls=image_urls)
                ext_id = str(result.get("id", ""))
                await update_log_status(log_id, "success", external_id=ext_id)
                results["instagram"] = {"status": "success", "external_id": ext_id}
                logger.info("Published carousel %s to instagram: %s", draft_id, ext_id)
            except Exception as exc:
                error_msg = str(exc)[:500]
                await update_log_status(log_id, "failed", error_message=error_msg)
                results["instagram"] = {"status": "failed", "error": error_msg}
                logger.error("Failed to publish carousel %s to instagram: %s", draft_id, exc)
            remaining_platforms = [p for p in remaining_platforms if p != "instagram"]

        if "threads" in remaining_platforms:
            log_id = await save_log(draft_id, "threads", "publish", "pending")
            try:
                image_url = _get_public_image_url(draft.payload or {}, draft.kind, draft_id, media_paths)
                result = await publish_to_threads(caption, image_url=image_url)
                ext_id = str(result.get("id", ""))
                await update_log_status(log_id, "success", external_id=ext_id)
                results["threads"] = {"status": "success", "external_id": ext_id}
                logger.info("Published carousel %s to threads: %s", draft_id, ext_id)
            except Exception as exc:
                error_msg = str(exc)[:500]
                await update_log_status(log_id, "failed", error_message=error_msg)
                results["threads"] = {"status": "failed", "error": error_msg}
                logger.error("Failed to publish carousel %s to threads: %s", draft_id, exc)
            remaining_platforms = [p for p in remaining_platforms if p != "threads"]

    upload_platforms = [p for p in remaining_platforms if p in UPLOAD_POST_PLATFORMS]
    if upload_platforms:
        result = await _upload_post_publish(draft_id, upload_platforms, scheduled_at)
        results.update(result)

    if "telegram" in remaining_platforms and telegram_bot and telegram_chat_id:
        result = await _telegram_publish(draft_id, telegram_bot, telegram_chat_id)
        results["telegram"] = result

    if "tiktok" in remaining_platforms:
        results["tiktok"] = await _tiktok_publish(draft_id)

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
