"""Publisher for Instagram & Threads via upload-post.com SDK."""

from __future__ import annotations

import asyncio
import logging
import os
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

# Module-level flag — once user profile is ensured we skip further create_user calls.
_user_ensured: set[str] = set()
_user_ensured_lock = asyncio.Lock()


async def _get_upload_credentials() -> tuple[str, str]:
    """(api_key, user) from BrandSettings DB, fallback to .env."""
    from bot.services.brand_settings_store import get_brand_settings

    bs = await get_brand_settings()
    api_key = (getattr(bs, "upload_post_api_key", "") or "").strip() or settings.upload_post_api_key
    user = (getattr(bs, "upload_post_user", "") or "").strip() or settings.upload_post_user
    return api_key, user


def _get_upload_client(api_key: str | None = None) -> UploadPostClient:
    key = api_key or settings.upload_post_api_key
    if not key:
        raise RuntimeError("UPLOAD_POST_API_KEY is not configured")
    return UploadPostClient(key)


async def _ensure_user(client: UploadPostClient, user: str) -> None:
    """Create upload-post user profile if not yet ensured this session."""
    async with _user_ensured_lock:
        if user in _user_ensured:
            return
        try:
            client.create_user(user)
            logger.info("upload-post: ensured user profile '%s'", user)
        except Exception as exc:
            # create_user may fail if user already exists — that's OK
            msg = str(exc).lower()
            if "already" in msg or "exists" in msg or "duplicate" in msg:
                logger.debug("upload-post: user '%s' already exists", user)
            else:
                logger.warning("upload-post: create_user('%s') failed: %s", user, exc)
        _user_ensured.add(user)


def _sanitize_filename(filename: str) -> str:
    """Strip directory components and reject path traversal attempts."""
    filename = os.path.basename(filename)
    if ".." in filename or "/" in filename or "\\" in filename:
        raise ValueError(f"Invalid filename: {filename}")
    return filename


def _resolve_media_paths(draft_kind: str, draft_id: str, payload: dict[str, Any]) -> list[Path]:
    """Resolve absolute file paths for media in a draft."""
    paths: list[Path] = []
    if draft_kind == "carousel":
        slide_images = payload.get("slide_images") or []
        for item in slide_images:
            if not item:
                continue
            raw_filename = str(item.get("filename", "")).strip()
            if raw_filename:
                filename = _sanitize_filename(raw_filename)
                path = CAROUSEL_ASSETS_DIR / draft_id / filename
                if path.exists():
                    paths.append(path)
    elif draft_kind in ("threads", "instagram"):
        image_info = payload.get("image")
        if isinstance(image_info, dict):
            raw_filename = str(image_info.get("filename", "")).strip()
            if raw_filename:
                filename = _sanitize_filename(raw_filename)
                path = CAROUSEL_ASSETS_DIR / draft_id / filename
                if path.exists():
                    paths.append(path)
    return paths


def _draft_text(payload: dict[str, Any], kind: str) -> str:
    """Extract the main text content from draft payload."""
    if kind == "carousel":
        # Prefer explicit caption field; fall back to joined slide texts
        caption = str(payload.get("caption", "") or "").strip()
        if caption:
            return caption
        slides = payload.get("slides") or []
        return "\n\n".join(str(s) for s in slides if s)
    for key in ("text", "post", "caption"):
        value = str(payload.get(key, "") or "").strip()
        if value:
            return value
    # Build from structured fields if no single text field
    parts = []
    for key in ("hook", "angle", "cta"):
        value = str(payload.get(key, "") or "").strip()
        if value:
            parts.append(value)
    return "\n\n".join(parts)


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

    api_key, user = await _get_upload_credentials()
    if not user:
        raise RuntimeError("UPLOAD_POST_USER is not configured")
    client = _get_upload_client(api_key)
    await _ensure_user(client, user)

    text = _draft_text(draft.payload, draft.kind)
    media_paths = _resolve_media_paths(draft.kind, draft_id, draft.payload)

    if not text.strip():
        raise ValueError("Draft has no publishable text content")

    if not media_paths and "instagram" in target_platforms:
        target_platforms = [p for p in target_platforms if p != "instagram"]
        if not target_platforms:
            raise ValueError("Instagram requires media. No media found in draft.")

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
            from bot.handlers.monitor import notify_owner
            notify_owner(f"⚠️ Publish to {platform} failed for draft {draft_id}:\n{error_msg}")

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
