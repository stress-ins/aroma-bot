from __future__ import annotations

from bot.agents.reels_agent import generate_reels_director_sync
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
                "asset_ready": bool(
                    isinstance(frame.get("current_asset"), dict) and frame["current_asset"].get("url")
                ),
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


async def build_reels_export_payload(draft_id: str) -> dict[str, object] | None:
    """v1 export — kept for backward compat."""
    reel = await serialize_reels_draft(draft_id)
    if not reel:
        return None

    frames = reel.get("frames", [])
    ready_frames = 0
    if isinstance(frames, list):
        for frame in frames:
            if isinstance(frame, dict) and isinstance(frame.get("current_asset"), dict) and frame["current_asset"].get("url"):
                ready_frames += 1

    return {
        "draft_id": reel.get("draft_id", draft_id),
        "topic": reel.get("topic", ""),
        "status": reel.get("status", ""),
        "source": reel.get("source", ""),
        "scenario": reel.get("payload", {}).get("scenario", "") if isinstance(reel.get("payload"), dict) else "",
        "images_ready": reel.get("images_ready", 0),
        "frame_count": reel.get("frame_count", 0),
        "ready_frames": ready_frames,
        "frames": frames,
        "shot_list": reel.get("shot_list", []),
        "production_notes": reel.get("production_notes", {"required": [], "optional": []}),
        "export_summary": {
            "ready": ready_frames == int(reel.get("frame_count", 0) or 0),
            "generated_assets": ready_frames,
            "missing_assets": max(int(reel.get("frame_count", 0) or 0) - ready_frames, 0),
        },
    }


async def update_reels_frame_note(draft_id: str, frame_index: int, note: str) -> dict[str, object] | None:
    draft = await get_draft(draft_id)
    if not draft or draft.kind not in ("reels", "reels_v2"):
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
    updated = await update_draft(draft_id, payload=payload, status="draft")
    if not updated:
        return None
    return await serialize_reels_draft(draft_id)


async def update_reels_frame_prompt(draft_id: str, frame_index: int, prompt: str) -> dict[str, object] | None:
    draft = await get_draft(draft_id)
    if not draft or draft.kind not in ("reels", "reels_v2"):
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
    updated = await update_draft(draft_id, payload=payload, status="draft")
    if not updated:
        return None
    return await serialize_reels_draft(draft_id)


async def update_reels_scenario(draft_id: str, scenario: str, concept: str = "") -> dict[str, object] | None:
    draft = await get_draft(draft_id)
    if not draft or draft.kind not in ("reels", "reels_v2"):
        return None
    payload = dict(draft.payload)
    payload["scenario"] = scenario.strip()
    payload["concept"] = concept.strip()
    updated = await update_draft(draft_id, payload=payload, status="draft")
    if not updated:
        return None
    return await serialize_reels_draft(draft_id)


async def update_reels_frame_fields(
    draft_id: str,
    frame_index: int,
    *,
    scene: str,
    angle: str,
    timecode: str,
) -> dict[str, object] | None:
    draft = await get_draft(draft_id)
    if not draft or draft.kind not in ("reels", "reels_v2"):
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
            frame["scene"] = scene.strip()
            frame["angle"] = angle.strip()
            frame["timecode"] = timecode.strip()
        updated_storyboard.append(frame)

    payload = dict(draft.payload)
    payload["storyboard"] = updated_storyboard
    updated = await update_draft(draft_id, payload=payload, status="draft")
    if not updated:
        return None
    return await serialize_reels_draft(draft_id)


async def regenerate_reels_storyboard(draft_id: str) -> dict[str, object] | None:
    draft = await get_draft(draft_id)
    if not draft or draft.kind not in ("reels", "reels_v2"):
        return None

    payload = dict(draft.payload)
    scenario = str(payload.get("scenario", "")).strip()
    frames = generate_reels_director_sync(draft.topic, scenario)
    payload["storyboard"] = [
        {
            "timecode": frame.timecode,
            "scene": frame.scene,
            "angle": frame.angle,
            "gemini_prompt": frame.gemini_prompt,
            "review_note": "",
            "prompt_revisions": [],
            "current_asset": {},
            "asset_revisions": [],
        }
        for frame in frames
    ]
    payload["images_ready"] = 0
    updated = await update_draft(draft_id, payload=payload, status="draft")
    if not updated:
        return None
    return await serialize_reels_draft(draft_id)


async def serialize_reels_draft(draft_id: str) -> dict[str, object] | None:
    """Serialize a reels_v2 (or legacy reels) draft for the MiniApp."""
    draft = await get_draft(draft_id)
    if not draft or draft.kind not in ("reels_v2", "reels"):
        return None

    data = await serialize_draft(draft)

    if draft.kind == "reels_v2":
        frames_raw = draft.payload.get("frames", [])
        frames: list[dict[str, object]] = []
        if isinstance(frames_raw, list):
            for item in frames_raw:
                if not isinstance(item, dict):
                    continue
                frames.append(
                    {
                        "id": str(item.get("id", "")),
                        "n": int(item.get("n", 0)),
                        "timecode": str(item.get("timecode", "")),
                        "overlay_text": str(item.get("overlay_text", "")),
                        "image_prompt": str(item.get("image_prompt", "")),
                        "image_url": str(item.get("image_url", "")),
                        "image_status": str(item.get("image_status", "pending")),
                        "image_versions": list(item.get("image_versions", [])) if isinstance(item.get("image_versions"), list) else [],
                    }
                )

        data["frames"] = frames
        data["frame_count"] = len(frames)
        data["images_ready"] = int(draft.payload.get("images_ready", 0) or 0)
        data["concept"] = str(draft.payload.get("concept", ""))
        data["hook"] = str(draft.payload.get("hook", ""))
        data["scenario"] = str(draft.payload.get("scenario", ""))
        data["caption"] = str(draft.payload.get("caption", ""))
        data["music_mood"] = str(draft.payload.get("music_mood", ""))
        data["approved"] = bool(draft.payload.get("approved", False))
        data["shooting_deadline_days"] = int(draft.payload.get("shooting_deadline_days", 0) or 0)
        data["feedback"] = draft.payload.get("feedback", {}) if isinstance(draft.payload.get("feedback"), dict) else {}
    else:
        storyboard_raw = draft.payload.get("storyboard", [])
        v1_frames: list[dict[str, object]] = []
        if isinstance(storyboard_raw, list):
            for idx, frame in enumerate(storyboard_raw):
                if not isinstance(frame, dict):
                    continue
                v1_frames.append(
                    {
                        "frame_index": idx,
                        "timecode": str(frame.get("timecode", "")),
                        "scene": str(frame.get("scene", "")),
                        "angle": str(frame.get("angle", "")),
                        "gemini_prompt": str(frame.get("gemini_prompt", "")),
                        "review_note": str(frame.get("review_note", "")),
                        "prompt_revisions": list(frame.get("prompt_revisions", [])) if isinstance(frame.get("prompt_revisions"), list) else [],
                        "current_asset": dict(frame.get("current_asset", {})) if isinstance(frame.get("current_asset"), dict) else {},
                        "asset_revisions": list(frame.get("asset_revisions", [])) if isinstance(frame.get("asset_revisions"), list) else [],
                    }
                )

        data["frames"] = v1_frames
        data["frame_count"] = len(v1_frames)
        data["images_ready"] = int(draft.payload.get("images_ready", 0) or 0)
        data["shot_list"] = _build_shot_list(v1_frames)
        data["production_notes"] = _build_production_notes(v1_frames)

    return data


async def list_reels_drafts(limit: int = 30) -> list[dict[str, object]]:
    drafts = await list_recent_drafts(limit=200, kind="reels_v2")
    if not drafts:
        drafts = await list_recent_drafts(limit=200, kind="reels")
    items: list[dict[str, object]] = []
    for draft in drafts[:limit]:
        data = await serialize_reels_draft(draft.draft_id)
        if data:
            items.append(data)
    return items


async def update_frame_field(
    draft_id: str,
    frame_id: str,
    *,
    overlay_text: str | None = None,
    image_prompt: str | None = None,
) -> dict[str, object] | None:
    draft = await get_draft(draft_id)
    if not draft or draft.kind != "reels_v2":
        return None
    frames = draft.payload.get("frames", [])
    if not isinstance(frames, list):
        return None

    updated_frames: list[dict[str, object]] = []
    found = False
    for item in frames:
        if not isinstance(item, dict):
            updated_frames.append({})
            continue
        frame = dict(item)
        if str(frame.get("id", "")) == frame_id:
            found = True
            if overlay_text is not None:
                frame["overlay_text"] = overlay_text.strip()
            if image_prompt is not None:
                frame["image_prompt"] = image_prompt.strip()
        updated_frames.append(frame)

    if not found:
        return None

    payload = dict(draft.payload)
    payload["frames"] = updated_frames
    updated = await update_draft(draft_id, payload=payload, status="draft")
    if not updated:
        return None
    return await serialize_reels_draft(draft_id)


async def update_concept(
    draft_id: str,
    *,
    concept: str,
    hook: str = "",
    scenario: str = "",
) -> dict[str, object] | None:
    draft = await get_draft(draft_id)
    if not draft or draft.kind != "reels_v2":
        return None
    payload = dict(draft.payload)
    payload["concept"] = concept.strip()
    if hook:
        payload["hook"] = hook.strip()
    if scenario:
        payload["scenario"] = scenario.strip()
    updated = await update_draft(draft_id, payload=payload, status="draft")
    if not updated:
        return None
    return await serialize_reels_draft(draft_id)


async def update_caption(
    draft_id: str,
    caption: str,
) -> dict[str, object] | None:
    draft = await get_draft(draft_id)
    if not draft or draft.kind != "reels_v2":
        return None
    payload = dict(draft.payload)
    payload["caption"] = caption.strip()
    updated = await update_draft(draft_id, payload=payload, status="draft")
    if not updated:
        return None
    return await serialize_reels_draft(draft_id)


async def approve_reels(
    draft_id: str,
    *,
    shooting_deadline_days: int = 3,
) -> dict[str, object] | None:
    draft = await get_draft(draft_id)
    if not draft or draft.kind != "reels_v2":
        return None
    payload = dict(draft.payload)
    payload["approved"] = True
    payload["shooting_deadline_days"] = shooting_deadline_days
    updated = await update_draft(draft_id, payload=payload, status="approved")
    if not updated:
        return None
    return await serialize_reels_draft(draft_id)


async def record_feedback(
    draft_id: str,
    *,
    platform: str,
    rating: int,
    reaction_types: list[str],
) -> dict[str, object] | None:
    draft = await get_draft(draft_id)
    if not draft or draft.kind != "reels_v2":
        return None
    payload = dict(draft.payload)
    payload["feedback"] = {
        "platform": platform,
        "rating": rating,
        "reaction_types": reaction_types,
    }
    updated = await update_draft(draft_id, payload=payload, status="draft")
    if not updated:
        return None
    return await serialize_reels_draft(draft_id)
