from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from bot.services.drafts_store import get_draft, update_draft
from bot.services.gemini_images import generate_gemini_image_sync


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


def regenerate_reels_frame_asset(draft_id: str, frame_index: int) -> dict[str, object] | None:
    draft = get_draft(draft_id)
    if not draft or draft.kind != "reels":
        return None
    storyboard = draft.payload.get("storyboard", [])
    if not isinstance(storyboard, list) or frame_index < 0 or frame_index >= len(storyboard):
        return None

    updated_storyboard: list[dict[str, object]] = []
    current_prompt = ""
    asset_count = 0
    for idx, item in enumerate(storyboard):
        if not isinstance(item, dict):
            updated_storyboard.append({})
            continue
        frame = dict(item)
        if idx == frame_index:
            current_prompt = str(frame.get("gemini_prompt", "")).strip()
            if not current_prompt:
                return None
            image = generate_gemini_image_sync(current_prompt, log_context="MiniApp reels frame regenerate")
            if not image:
                return None
            asset = save_reels_frame_asset(draft_id, frame_index, image, prompt=current_prompt)
            revisions = list(frame.get("asset_revisions", [])) if isinstance(frame.get("asset_revisions"), list) else []
            current_asset = frame.get("current_asset")
            if isinstance(current_asset, dict) and current_asset.get("url"):
                revisions.append(dict(current_asset))
            frame["current_asset"] = asset
            frame["asset_revisions"] = revisions[-5:]
        if isinstance(frame.get("current_asset"), dict) and frame["current_asset"].get("url"):
            asset_count += 1
        updated_storyboard.append(frame)

    payload = dict(draft.payload)
    payload["storyboard"] = updated_storyboard
    payload["images_ready"] = max(int(payload.get("images_ready", 0) or 0), asset_count)
    updated = update_draft(draft_id, payload=payload, status="draft")
    if not updated:
        return None
    return payload
