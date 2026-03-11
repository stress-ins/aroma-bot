from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from bot.services.drafts_store import get_draft, update_draft
from bot.services.gemini_images import generate_gemini_image_sync

logger = logging.getLogger(__name__)

ASSETS_DIR = Path(__file__).parent.parent.parent / "data" / "reels_assets"
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


def populate_reels_frame_assets(
    draft_id: str,
    *,
    frame_indexes: list[int] | None = None,
    overwrite_existing: bool = False,
) -> dict[str, object] | None:
    draft = get_draft(draft_id)
    if not draft or draft.kind != "reels":
        return None
    storyboard = draft.payload.get("storyboard", [])
    if not isinstance(storyboard, list):
        return None

    allowed_indexes = set(frame_indexes) if frame_indexes is not None else None
    updated_storyboard: list[dict[str, object]] = []
    asset_count = 0
    generated_any = False

    def persist_progress() -> bool:
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
        updated = update_draft(draft_id, payload=payload, status="draft")
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
                image = generate_gemini_image_sync(current_prompt, log_context=f"MiniApp reels frame {idx + 1}")
                if image:
                    asset = save_reels_frame_asset(draft_id, idx, image, prompt=current_prompt)
                    revisions = list(frame.get("asset_revisions", [])) if isinstance(frame.get("asset_revisions"), list) else []
                    current_asset = frame.get("current_asset")
                    if isinstance(current_asset, dict) and current_asset.get("url"):
                        revisions.append(dict(current_asset))
                    frame["current_asset"] = asset
                    frame["asset_revisions"] = revisions[-5:]
                    generated_any = True
                    updated_storyboard.append(frame)
                    if not persist_progress():
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
    updated = update_draft(draft_id, payload=payload, status="draft")
    if not updated:
        return None
    if allowed_indexes and not generated_any and asset_count == 0:
        return None
    return payload


def regenerate_reels_frame_asset(draft_id: str, frame_index: int) -> dict[str, object] | None:
    draft = get_draft(draft_id)
    storyboard = draft.payload.get("storyboard", []) if draft else []
    if not draft or draft.kind != "reels" or not isinstance(storyboard, list) or frame_index < 0 or frame_index >= len(storyboard):
        return None
    return populate_reels_frame_assets(
        draft_id,
        frame_indexes=[frame_index],
        overwrite_existing=True,
    )
