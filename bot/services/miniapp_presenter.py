from __future__ import annotations

from typing import Any

from sqlalchemy import select

from bot.services.drafts_store import DraftRecord
from db.models import TeamMemberModel
from db.session import AsyncSessionLocal


async def filter_drafts(
    records: list[DraftRecord],
    *,
    kind: str = "",
    status: str = "",
    feedback: str = "",
    query: str = "",
) -> list[DraftRecord]:
    kind = kind.strip().lower()
    status = status.strip().lower()
    feedback = feedback.strip().lower()
    query = query.strip().lower()

    filtered = records
    if kind:
        # "threads" filter should also match "threads_series"
        match_kinds = {kind, "threads_series"} if kind == "threads" else {kind}
        filtered = [record for record in filtered if record.kind.lower() in match_kinds]
    if status:
        filtered = [record for record in filtered if record.status.lower() == status]
    if feedback:
        filtered = [record for record in filtered if record.feedback.lower() == feedback]
    if query:
        filtered = [
            record
            for record in filtered
            if query in record.topic.lower()
            or query in record.source.lower()
            or query in record.kind.lower()
        ]
    return filtered


def payload_preview(kind: str, payload: dict[str, Any]) -> str:
    if kind == "reels":
        return str(payload.get("scenario", "")).strip()[:220]

    if kind == "threads_series":
        summary = str(payload.get("series_summary", "")).strip()
        if summary:
            return summary[:220]
        posts = payload.get("posts")
        if isinstance(posts, list) and posts:
            first_text = str(posts[0].get("text", "")).strip() if isinstance(posts[0], dict) else ""
            if first_text:
                return first_text[:220]
        return str(payload.get("angle", "")).strip()[:220]

    if kind == "youtube_video":
        title = str(payload.get("title", "")).strip()
        sections = payload.get("sections", [])
        subformat = payload.get("subformat", "")
        subformat_labels = {"talking_head": "Talking Head", "listicle": "Listicle", "podcast": "Подкаст"}
        parts = []
        if subformat:
            parts.append(subformat_labels.get(subformat, subformat))
        dur = payload.get("duration_target")
        if dur:
            parts.append(f"~{dur} мин")
        if sections:
            parts.append(f"{len(sections)} секций")
        meta = " · ".join(parts)
        if title:
            return f"{meta}: {title}"[:220] if meta else title[:220]
        return meta[:220] if meta else ""

    # For carousels, prefer hook/angle (concept summary) over individual slide text
    if kind == "carousel":
        for key in ("hook", "angle"):
            value = str(payload.get(key, "")).strip()
            if value:
                return value[:220]

    slides = payload.get("slides")
    if isinstance(slides, list) and slides:
        text = " / ".join(str(item).strip() for item in slides[:2] if str(item).strip())
        if text:
            return text[:220]

    for key in ("caption", "hook", "angle", "cta"):
        value = str(payload.get(key, "")).strip()
        if value:
            return value[:220]
    return ""



async def _resolve_username(telegram_id: int | None) -> str:
    if not telegram_id:
        return ""
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(TeamMemberModel.username)
                .where(TeamMemberModel.telegram_id == telegram_id)
                .limit(1)
            )
            row = result.scalar_one_or_none()
            return row or ""
    except Exception:
        return ""


async def serialize_draft(record: DraftRecord) -> dict[str, Any]:
    payload = dict(record.payload)
    slides_count = len(payload.get("slides", [])) if isinstance(payload.get("slides"), list) else 0
    storyboard_count = len(payload.get("storyboard", [])) if isinstance(payload.get("storyboard"), list) else 0
    images_ready = int(payload.get("images_ready", 0) or 0)
    generation_stage = str(payload.get("generation_stage", ""))
    has_error = generation_stage == "error"
    is_awaiting_callback = generation_stage == "awaiting_callback"
    explicit_pending = bool(payload.get("generation_pending"))
    generation_pending = explicit_pending
    # Don't derive pending from missing images when generation failed or awaits webhook
    if not has_error and not is_awaiting_callback:
        if record.kind == "carousel" and slides_count:
            generation_pending = generation_pending or images_ready < slides_count
        if record.kind == "reels" and storyboard_count:
            generation_pending = generation_pending or images_ready < storyboard_count
    from bot.services.image_thumbs import enrich_image_dict
    if isinstance(payload.get("slide_images"), list):
        payload["slide_images"] = [enrich_image_dict(img) for img in payload["slide_images"]]

    # Check avatar existence: from payload path or team avatar on disk
    has_avatar = bool(payload.get("brand_avatar_path"))
    if not has_avatar and record.team_id:
        from pathlib import Path
        team_avatar = Path(__file__).parent.parent.parent / "data" / "avatars" / f"team_{record.team_id}.jpg"
        has_avatar = team_avatar.exists()

    created_by_username = await _resolve_username(record.created_by)
    return {
        "draft_id": record.draft_id,
        "seq_id": record.seq_id,
        "kind": record.kind,
        "topic": record.topic,
        "source": record.source,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "status": record.status,
        "feedback": record.feedback,
        "preview": payload_preview(record.kind, payload),
        "slides_count": slides_count,
        "storyboard_count": storyboard_count,
        "images_ready": images_ready,
        "generation_pending": generation_pending,
        "generation_stage": generation_stage,
        "generation_message": str(payload.get("generation_message", "")),
        "generation_error": str(payload.get("generation_error", "")),
        "has_avatar": has_avatar,
        "created_by": record.created_by,
        "created_by_username": created_by_username,
        "payload": payload,
    }


async def serialize_draft_summary(record: DraftRecord) -> dict[str, Any]:
    payload = dict(record.payload)
    slides_count = len(payload.get("slides", [])) if isinstance(payload.get("slides"), list) else 0
    storyboard_count = len(payload.get("storyboard", [])) if isinstance(payload.get("storyboard"), list) else 0
    images_ready = int(payload.get("images_ready", 0) or 0)
    generation_stage = str(payload.get("generation_stage", ""))
    has_error = generation_stage == "error"
    is_awaiting_callback = generation_stage == "awaiting_callback"
    generation_pending = bool(payload.get("generation_pending"))
    if not has_error and not is_awaiting_callback:
        if record.kind == "carousel" and slides_count:
            generation_pending = generation_pending or images_ready < slides_count
        if record.kind == "reels" and storyboard_count:
            generation_pending = generation_pending or images_ready < storyboard_count
    return {
        "draft_id": record.draft_id,
        "seq_id": record.seq_id,
        "kind": record.kind,
        "topic": record.topic,
        "source": record.source,
        "created_at": record.created_at,
        "status": record.status,
        "feedback": record.feedback,
        "preview": payload_preview(record.kind, payload),
        "slides_count": slides_count,
        "storyboard_count": storyboard_count,
        "images_ready": images_ready,
        "generation_pending": generation_pending,
        "generation_stage": generation_stage,
        "generation_message": str(payload.get("generation_message", "")),
        "generation_error": str(payload.get("generation_error", "")),
        "created_by": record.created_by,
    }
