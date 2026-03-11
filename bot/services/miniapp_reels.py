from __future__ import annotations

from bot.services.drafts_store import get_draft, list_recent_drafts, update_draft
from bot.services.miniapp_presenter import serialize_draft


def _build_shot_list(frames: list[dict[str, object]]) -> list[dict[str, object]]:
    shots: list[dict[str, object]] = []
    for frame in frames:
        shots.append(
            {
                "frame_index": int(frame.get("frame_index", 0)),
                "title": f"Shot {int(frame.get('frame_index', 0)) + 1}",
                "timecode": str(frame.get("timecode", "")),
                "camera": str(frame.get("angle", "")),
                "action": str(frame.get("scene", "")),
                "note": str(frame.get("review_note", "")),
            }
        )
    return shots


def _build_production_notes(frames: list[dict[str, object]]) -> dict[str, list[str]]:
    required = []
    optional = []
    for frame in frames:
        title = f"{frame.get('timecode', '')}: {frame.get('scene', '')}".strip(": ")
        camera = str(frame.get("angle", "")).strip()
        note = str(frame.get("review_note", "")).strip()
        if title:
            required.append(title)
        if camera:
            optional.append(f"Камера: {camera}")
        if note:
            optional.append(f"Note: {note}")
    return {
        "required": required[:6],
        "optional": optional[:8],
    }


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
                    "review_note": str(frame.get("review_note", "")),
                    "prompt_revisions": list(frame.get("prompt_revisions", [])) if isinstance(frame.get("prompt_revisions"), list) else [],
                }
            )

    data["frames"] = frames
    data["frame_count"] = len(frames)
    data["images_ready"] = int(draft.payload.get("images_ready", 0) or 0)
    data["shot_list"] = _build_shot_list(frames)
    data["production_notes"] = _build_production_notes(frames)
    return data


def list_reels_drafts(limit: int = 30) -> list[dict[str, object]]:
    drafts = list_recent_drafts(limit=200, kind="reels")
    items: list[dict[str, object]] = []
    for draft in drafts[:limit]:
        data = serialize_reels_draft(draft.draft_id)
        if data:
            items.append(data)
    return items


def update_reels_frame_note(draft_id: str, frame_index: int, note: str) -> dict[str, object] | None:
    draft = get_draft(draft_id)
    if not draft or draft.kind != "reels":
        return None
    storyboard = draft.payload.get("storyboard", [])
    if not isinstance(storyboard, list) or frame_index < 0 or frame_index >= len(storyboard):
        return None

    updated_storyboard: list[dict[str, object]] = []
    for idx, item in enumerate(storyboard):
        if not isinstance(item, dict):
            updated_storyboard.append({})
            continue
        frame = dict(item)
        if idx == frame_index:
            frame["review_note"] = note.strip()
        updated_storyboard.append(frame)

    payload = dict(draft.payload)
    payload["storyboard"] = updated_storyboard
    updated = update_draft(draft_id, payload=payload, status="draft")
    if not updated:
        return None
    return serialize_reels_draft(draft_id)


def update_reels_frame_prompt(draft_id: str, frame_index: int, prompt: str) -> dict[str, object] | None:
    draft = get_draft(draft_id)
    if not draft or draft.kind != "reels":
        return None
    storyboard = draft.payload.get("storyboard", [])
    if not isinstance(storyboard, list) or frame_index < 0 or frame_index >= len(storyboard):
        return None

    updated_storyboard: list[dict[str, object]] = []
    for idx, item in enumerate(storyboard):
        if not isinstance(item, dict):
            updated_storyboard.append({})
            continue
        frame = dict(item)
        if idx == frame_index:
            current_prompt = str(frame.get("gemini_prompt", "")).strip()
            new_prompt = prompt.strip()
            revisions = list(frame.get("prompt_revisions", [])) if isinstance(frame.get("prompt_revisions"), list) else []
            if current_prompt and current_prompt != new_prompt:
                revisions.append(current_prompt)
            frame["gemini_prompt"] = new_prompt
            frame["prompt_revisions"] = revisions[-5:]
        updated_storyboard.append(frame)

    payload = dict(draft.payload)
    payload["storyboard"] = updated_storyboard
    updated = update_draft(draft_id, payload=payload, status="draft")
    if not updated:
        return None
    return serialize_reels_draft(draft_id)
