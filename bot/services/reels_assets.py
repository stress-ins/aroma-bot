from __future__ import annotations

import asyncio
import functools
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from bot.services.drafts_store import get_draft, update_draft
from bot.services.gemini_images import ImageGenResult, generate_gemini_image_sync, recover_kie_task_sync


def _get_reels_model() -> str:
    """Get configured reels image model, with fallback."""
    try:
        from bot.services.brand_settings_store import get_brand_settings_cached
        bs = get_brand_settings_cached()
        return bs.image_model_reels or "gpt-image/1.5-text-to-image"
    except Exception:
        return "gpt-image/1.5-text-to-image"

logger = logging.getLogger(__name__)

ASSETS_DIR = Path(os.getenv("AROMA_REELS_ASSETS_DIR", Path(__file__).parent.parent.parent / "data" / "reels_assets"))
ASSETS_DIR.mkdir(parents=True, exist_ok=True)


def _ensure_assets_dir(draft_id: str) -> Path:
    path = ASSETS_DIR / draft_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_reels_frame_asset(draft_id: str, frame_index: int, image_bytes: bytes, *, prompt: str) -> dict[str, str]:
    directory = _ensure_assets_dir(draft_id)
    generated_at = datetime.now(timezone.utc).isoformat()
    filename = f"frame_{frame_index + 1}_{uuid4().hex[:8]}.png"
    file_path = directory / filename
    file_path.write_bytes(image_bytes)
    return {
        "filename": filename,
        "generated_at": generated_at,
        "url": f"/generated/reels_assets/{draft_id}/{filename}",
        "prompt": prompt,
    }


async def populate_reels_frame_assets(
    draft_id: str,
    *,
    frame_indexes: list[int] | None = None,
    overwrite_existing: bool = False,
) -> dict[str, object] | None:
    draft = await get_draft(draft_id)
    if not draft or draft.kind != "reels":
        return None
    storyboard = draft.payload.get("storyboard", [])
    if not isinstance(storyboard, list):
        return None

    allowed_indexes = set(frame_indexes) if frame_indexes is not None else None
    updated_storyboard: list[dict[str, object]] = []
    asset_count = 0
    generated_any = False

    async def persist_progress() -> bool:
        payload = dict(draft.payload)
        payload["storyboard"] = updated_storyboard + [
            dict(item) if isinstance(item, dict) else {}
            for item in storyboard[len(updated_storyboard):]
        ]
        payload["images_ready"] = sum(
            1
            for frame in payload["storyboard"]
            if isinstance(frame, dict)
            and isinstance(frame.get("current_asset"), dict)
            and frame["current_asset"].get("url")
        )
        updated = await update_draft(draft_id, payload=payload, status="draft")
        return updated is not None

    for idx, item in enumerate(storyboard):
        if not isinstance(item, dict):
            updated_storyboard.append({})
            continue

        frame = dict(item)
        has_current_asset = isinstance(frame.get("current_asset"), dict) and bool(frame["current_asset"].get("url"))
        should_generate = (
            allowed_indexes is None or idx in allowed_indexes
        ) and (overwrite_existing or not has_current_asset)

        if should_generate:
            current_prompt = str(frame.get("gemini_prompt", "")).strip()
            if current_prompt:
                result = await asyncio.get_running_loop().run_in_executor(
                    None,
                    functools.partial(
                        generate_gemini_image_sync,
                        current_prompt,
                        aspect_ratio="9:16",
                        log_context=f"MiniApp reels frame {idx + 1}",
                        model=_get_reels_model(),
                        draft_id=draft_id,
                        content_type="reels_frame",
                        slot_key=str(idx),
                    ),
                )
                if result.kie_task_id:
                    frame["kie_task_id"] = result.kie_task_id
                if result.image_bytes:
                    asset = save_reels_frame_asset(draft_id, idx, result.image_bytes, prompt=current_prompt)
                    revisions = list(frame.get("asset_revisions", [])) if isinstance(frame.get("asset_revisions"), list) else []
                    current_asset = frame.get("current_asset")
                    if isinstance(current_asset, dict) and current_asset.get("url"):
                        revisions.append(dict(current_asset))
                    frame["current_asset"] = asset
                    frame["asset_revisions"] = revisions[-5:]
                    frame.pop("kie_task_id", None)
                    generated_any = True
                    updated_storyboard.append(frame)
                    if not await persist_progress():
                        return None
                    if isinstance(frame.get("current_asset"), dict) and frame["current_asset"].get("url"):
                        asset_count += 1
                    continue
                else:
                    logger.warning("MiniApp reels frame %s asset generation returned no image for draft %s", idx + 1, draft_id)

        if isinstance(frame.get("current_asset"), dict) and frame["current_asset"].get("url"):
            asset_count += 1
        updated_storyboard.append(frame)

    payload = dict(draft.payload)
    payload["storyboard"] = updated_storyboard
    payload["images_ready"] = asset_count
    updated = await update_draft(draft_id, payload=payload, status="draft")
    if not updated:
        return None
    if allowed_indexes and not generated_any and asset_count == 0:
        return None
    return payload


async def regenerate_reels_frame_asset(draft_id: str, frame_index: int) -> dict[str, object] | None:
    """v1 regenerate by frame index — kept for backward compat."""
    draft = await get_draft(draft_id)
    storyboard = draft.payload.get("storyboard", []) if draft else []
    if not draft or draft.kind != "reels" or not isinstance(storyboard, list) or frame_index < 0 or frame_index >= len(storyboard):
        return None
    return await populate_reels_frame_assets(
        draft_id,
        frame_indexes=[frame_index],
        overwrite_existing=True,
    )


def save_frame_asset(draft_id: str, frame_id: str, image_bytes: bytes, *, prompt: str) -> dict[str, str]:
    """Save image bytes for a v2 frame (identified by UUID)."""
    directory = _ensure_assets_dir(draft_id)
    generated_at = datetime.now(timezone.utc).isoformat()
    filename = f"frame_{frame_id[:8]}_{uuid4().hex[:8]}.png"
    file_path = directory / filename
    file_path.write_bytes(image_bytes)
    return {
        "filename": filename,
        "generated_at": generated_at,
        "url": f"/generated/reels_assets/{draft_id}/{filename}",
        "prompt": prompt,
    }


async def populate_frame_assets(
    draft_id: str,
    *,
    frame_ids: list[str] | None = None,
    overwrite_existing: bool = False,
) -> dict[str, object] | None:
    """Generate images for all (or specified) v2 frames."""
    draft = await get_draft(draft_id)
    if not draft or draft.kind != "reels_v2":
        return None
    frames_raw = draft.payload.get("frames", [])
    if not isinstance(frames_raw, list):
        return None

    allowed_ids = set(frame_ids) if frame_ids is not None else None
    updated_frames: list[dict[str, object]] = []
    images_ready = 0

    for item in frames_raw:
        if not isinstance(item, dict):
            updated_frames.append({})
            continue

        frame = dict(item)
        fid = str(frame.get("id", ""))
        has_url = bool(str(frame.get("image_url", "")).strip())
        should_generate = (
            allowed_ids is None or fid in allowed_ids
        ) and (overwrite_existing or not has_url)

        if should_generate:
            current_prompt = str(frame.get("image_prompt", "")).strip()
            if current_prompt:
                result = await asyncio.get_running_loop().run_in_executor(
                    None,
                    functools.partial(
                        generate_gemini_image_sync,
                        current_prompt,
                        aspect_ratio="9:16",
                        log_context=f"ReelsV2 frame {fid[:8]}",
                        model=_get_reels_model(),
                        draft_id=draft_id,
                        content_type="reels_v2_frame",
                        slot_key=fid,
                    ),
                )
                if result.kie_task_id:
                    frame["kie_task_id"] = result.kie_task_id
                if result.image_bytes:
                    asset = save_frame_asset(draft_id, fid, result.image_bytes, prompt=current_prompt)
                    versions = list(frame.get("image_versions", [])) if isinstance(frame.get("image_versions"), list) else []
                    if has_url:
                        versions.append({"url": frame["image_url"], "prompt": frame.get("image_prompt", "")})
                    frame["image_url"] = asset["url"]
                    frame["image_status"] = "ready"
                    frame["image_versions"] = versions[-5:]
                    frame.pop("placement_data", None)
                    frame.pop("kie_task_id", None)
                    images_ready += 1
                else:
                    frame["image_status"] = "error"
                    frame["error_message"] = result.error or "Генерация не вернула изображение"
                    logger.warning("ReelsV2 frame %s image generation failed for draft %s", fid, draft_id)
            else:
                frame["image_status"] = "pending"
        else:
            if has_url:
                images_ready += 1

        updated_frames.append(frame)

    payload = dict(draft.payload)
    payload["frames"] = updated_frames
    payload["images_ready"] = images_ready
    if allowed_ids and "frame_placement_data" in payload:
        fpd = payload["frame_placement_data"]
        if isinstance(fpd, dict):
            for fid in allowed_ids:
                fpd.pop(fid, None)
    updated = await update_draft(draft_id, payload=payload, status="draft")
    if not updated:
        return None
    return payload


async def regenerate_frame_asset(
    draft_id: str,
    frame_id: str,
    prompt: str | None = None,
) -> dict[str, object] | None:
    """Regenerate image for a single v2 frame. Optionally update the prompt first."""
    draft = await get_draft(draft_id)
    if not draft or draft.kind != "reels_v2":
        return None

    if prompt is not None:
        frames_raw = draft.payload.get("frames", [])
        if isinstance(frames_raw, list):
            updated_frames: list[dict[str, object]] = []
            for item in frames_raw:
                if not isinstance(item, dict):
                    updated_frames.append({})
                    continue
                frame = dict(item)
                if str(frame.get("id", "")) == frame_id:
                    frame["image_prompt"] = prompt.strip()
                updated_frames.append(frame)
            payload = dict(draft.payload)
            payload["frames"] = updated_frames
            await update_draft(draft_id, payload=payload, status="draft")

    return await populate_frame_assets(
        draft_id,
        frame_ids=[frame_id],
        overwrite_existing=True,
    )


async def recover_frame_asset(draft_id: str, frame_id: str) -> dict[str, object] | None:
    """Recover a frame image by re-polling its kie_task_id."""
    draft = await get_draft(draft_id)
    if not draft or draft.kind != "reels_v2":
        return None

    frames_raw = draft.payload.get("frames", [])
    if not isinstance(frames_raw, list):
        return None

    target_frame = None
    target_idx = -1
    for idx, item in enumerate(frames_raw):
        if isinstance(item, dict) and str(item.get("id", "")) == frame_id:
            target_frame = dict(item)
            target_idx = idx
            break

    if target_frame is None:
        return None

    kie_task_id = target_frame.get("kie_task_id")
    if not kie_task_id:
        return None

    result = recover_kie_task_sync(kie_task_id)
    if not result.image_bytes:
        return None

    asset = save_frame_asset(draft_id, frame_id, result.image_bytes, prompt=target_frame.get("image_prompt", ""))
    versions = list(target_frame.get("image_versions", [])) if isinstance(target_frame.get("image_versions"), list) else []
    old_url = target_frame.get("image_url", "")
    if old_url:
        versions.append({"url": old_url, "prompt": target_frame.get("image_prompt", "")})
    target_frame["image_url"] = asset["url"]
    target_frame["image_status"] = "ready"
    target_frame["image_versions"] = versions[-5:]
    target_frame.pop("kie_task_id", None)
    target_frame.pop("error_message", None)
    target_frame.pop("placement_data", None)

    updated_frames = []
    for idx, item in enumerate(frames_raw):
        if idx == target_idx:
            updated_frames.append(target_frame)
        else:
            updated_frames.append(dict(item) if isinstance(item, dict) else {})

    payload = dict(draft.payload)
    payload["frames"] = updated_frames
    images_ready = sum(1 for f in updated_frames if isinstance(f, dict) and bool(str(f.get("image_url", "")).strip()))
    payload["images_ready"] = images_ready
    updated = await update_draft(draft_id, payload=payload, status="draft")
    if not updated:
        return None
    return payload
