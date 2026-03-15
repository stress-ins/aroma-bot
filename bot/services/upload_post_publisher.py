"""Publisher for Instagram & Threads via upload-post.com SDK."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from upload_post import UploadPostClient

from config import settings
from bot.services.carousel_assets import CAROUSEL_ASSETS_DIR
from bot.services.drafts_store import get_draft
from bot.services.approval_workflow import mark_published, mark_failed
from bot.services.publish_log_store import save_log, update_log_status

logger = logging.getLogger(__name__)

UPLOAD_POST_PLATFORMS = {"threads", "instagram"}


def _get_upload_client() -> UploadPostClient:
    if not settings.upload_post_api_key:
        raise RuntimeError("UPLOAD_POST_API_KEY is not configured")
    return UploadPostClient(settings.upload_post_api_key)


def _resolve_media_paths(draft_kind: str, draft_id: str, payload: dict[str, Any]) -> list[Path]:
    """Resolve absolute file paths for media in a draft."""
    paths: list[Path] = []
    if draft_kind == "carousel":
        slide_images = payload.get("slide_images") or []
        for item in slide_images:
            if not item:
                continue
            filename = str(item.get("filename", "")).strip()
            if filename:
                path = CAROUSEL_ASSETS_DIR / draft_id / filename
                if path.exists():
                    paths.append(path)
    elif draft_kind in ("threads", "instagram"):
        image_info = payload.get("image")
        if isinstance(image_info, dict):
            filename = str(image_info.get("filename", "")).strip()
            if filename:
                path = CAROUSEL_ASSETS_DIR / draft_id / filename
                if path.exists():
                    paths.append(path)
    return paths


def _draft_text(payload: dict[str, Any], kind: str) -> str:
    """Extract the main text content from draft payload."""
    if kind == "carousel":
        slides = payload.get("slides") or []
        return "\n\n".join(str(s) for s in slides if s)
    return str(payload.get("text", "") or payload.get("post", ""))


async def publish_item(
    draft_id: str,
    platforms: list[str] | None = None,
    scheduled_at: datetime | None = None,
) -> dict[str, Any]:
    """Publish a draft to Instagram/Threads via upload-post.

    Calls mark_published or mark_failed from approval_workflow on completion.
    Returns dict of {platform: {status, external_id/error}}.
    """
    draft = await get_draft(draft_id)
    if not draft:
        raise ValueError(f"Draft {draft_id} not found")

    target_platforms = platforms or [p for p in draft.publish_platforms if p in UPLOAD_POST_PLATFORMS]
    if not target_platforms:
        return {}

    client = _get_upload_client()
    user = settings.upload_post_user
    if not user:
        raise RuntimeError("UPLOAD_POST_USER is not configured")

    text = _draft_text(draft.payload, draft.kind)
    media_paths = _resolve_media_paths(draft.kind, draft_id, draft.payload)

    kwargs: dict[str, Any] = {}
    if scheduled_at:
        kwargs["scheduled_date"] = scheduled_at.isoformat()
        kwargs["timezone"] = settings.timezone

    results: dict[str, Any] = {}
    action = "schedule" if scheduled_at else "publish"
    all_ok = True

    for platform in target_platforms:
        log_id = await save_log(draft_id, platform, action, "pending")
        try:
            if media_paths:
                response = client.upload_photos(
                    photos=[str(p) for p in media_paths],
                    title=text,
                    user=user,
                    platforms=[platform],
                    **kwargs,
                )
            else:
                response = client.upload_text(
                    title=text,
                    user=user,
                    platforms=[platform],
                    **kwargs,
                )
            external_id = str(response.get("request_id", "") or response.get("id", ""))
            await update_log_status(log_id, "success", external_id=external_id)
            results[platform] = {"status": "success", "external_id": external_id, "response": response}
            logger.info("Published draft %s to %s: %s", draft_id, platform, external_id)
        except Exception as exc:
            all_ok = False
            error_msg = str(exc)[:500]
            await update_log_status(log_id, "failed", error_message=error_msg)
            results[platform] = {"status": "failed", "error": error_msg}
            logger.error("Failed to publish draft %s to %s: %s", draft_id, platform, exc)

    # Update workflow status
    try:
        if all_ok and not scheduled_at:
            ext_ids = {p: info.get("external_id", "") for p, info in results.items() if isinstance(info, dict)}
            await mark_published(draft_id, ext_ids)
        elif not all_ok:
            errors = "; ".join(f"{p}: {info.get('error', '')}" for p, info in results.items() if isinstance(info, dict) and info.get("status") == "failed")
            await mark_failed(draft_id, errors)
    except Exception:
        logger.exception("Failed to update workflow status for draft %s", draft_id)

    return results


async def check_status(draft_id: str) -> dict[str, Any]:
    """Check publishing status via upload-post."""
    draft = await get_draft(draft_id)
    if not draft:
        return {"error": "Draft not found"}

    external_ids = draft.external_ids or {}
    if not external_ids:
        return {"error": "No external IDs found"}

    client = _get_upload_client()
    statuses: dict[str, Any] = {}
    for platform, ext_id in external_ids.items():
        if platform in UPLOAD_POST_PLATFORMS and ext_id:
            try:
                statuses[platform] = client.get_status(request_id=ext_id)
            except Exception as exc:
                statuses[platform] = {"error": str(exc)[:200]}
    return statuses


async def cancel_scheduled(draft_id: str) -> dict[str, Any]:
    """Cancel a scheduled publication."""
    from bot.services.drafts_store import update_draft

    draft = await get_draft(draft_id)
    if not draft:
        return {"error": "Draft not found"}

    external_ids = draft.external_ids or {}
    client = _get_upload_client()
    results: dict[str, Any] = {}
    for platform, ext_id in external_ids.items():
        if platform in UPLOAD_POST_PLATFORMS and ext_id:
            try:
                results[platform] = client.cancel_scheduled(job_id=ext_id)
                await save_log(draft_id, platform, "cancel", "success", external_id=ext_id)
            except Exception as exc:
                results[platform] = {"error": str(exc)[:200]}
                await save_log(draft_id, platform, "cancel", "failed", error_message=str(exc)[:500])

    await update_draft(draft_id, status="approved", scheduled_at=None)
    return results
