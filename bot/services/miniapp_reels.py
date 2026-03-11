from __future__ import annotations

from bot.services.drafts_store import get_draft, list_recent_drafts
from bot.services.miniapp_presenter import serialize_draft


def serialize_reels_draft(draft_id: str) -> dict[str, object] | None:
    draft = get_draft(draft_id)
    if not draft or draft.kind != "reels":
        return None

    data = serialize_draft(draft)
    storyboard_raw = draft.payload.get("storyboard", [])
    frames: list[dict[str, object]] = []
    if isinstance(storyboard_raw, list):
        for idx, frame in enumerate(storyboard_raw):
            if not isinstance(frame, dict):
                continue
            frames.append(
                {
                    "frame_index": idx,
                    "timecode": str(frame.get("timecode", "")),
                    "scene": str(frame.get("scene", "")),
                    "angle": str(frame.get("angle", "")),
                    "gemini_prompt": str(frame.get("gemini_prompt", "")),
                }
            )

    data["frames"] = frames
    data["frame_count"] = len(frames)
    data["images_ready"] = int(draft.payload.get("images_ready", 0) or 0)
    return data


def list_reels_drafts(limit: int = 30) -> list[dict[str, object]]:
    drafts = list_recent_drafts(limit=200, kind="reels")
    items: list[dict[str, object]] = []
    for draft in drafts[:limit]:
        data = serialize_reels_draft(draft.draft_id)
        if data:
            items.append(data)
    return items
