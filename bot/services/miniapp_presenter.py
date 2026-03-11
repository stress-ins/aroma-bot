from __future__ import annotations

from typing import Any

from bot.services.drafts_store import DraftRecord


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
        filtered = [record for record in filtered if record.kind.lower() == kind]
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


async def serialize_draft(record: DraftRecord) -> dict[str, Any]:
    payload = dict(record.payload)
    return {
        "draft_id": record.draft_id,
        "kind": record.kind,
        "topic": record.topic,
        "source": record.source,
        "created_at": record.created_at,
        "status": record.status,
        "feedback": record.feedback,
        "preview": payload_preview(record.kind, payload),
        "slides_count": len(payload.get("slides", [])) if isinstance(payload.get("slides"), list) else 0,
        "storyboard_count": len(payload.get("storyboard", [])) if isinstance(payload.get("storyboard"), list) else 0,
        "payload": payload,
    }
