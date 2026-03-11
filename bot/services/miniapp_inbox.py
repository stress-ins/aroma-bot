from __future__ import annotations

from bot.services.drafts_store import DraftRecord, list_recent_drafts
from bot.services.miniapp_presenter import payload_preview


REVIEW_STATUSES = {"draft", "in_review"}


def is_review_status(status: str) -> bool:
    return status.strip().lower() in REVIEW_STATUSES


def serialize_inbox_item(record: DraftRecord) -> dict[str, object]:
    return {
        "draft_id": record.draft_id,
        "kind": record.kind,
        "topic": record.topic,
        "source": record.source,
        "status": record.status,
        "feedback": record.feedback,
        "preview": payload_preview(record.kind, record.payload),
        "created_at": record.created_at,
    }


def list_inbox_items(limit: int = 100) -> list[dict[str, object]]:
    items = [
        serialize_inbox_item(record)
        for record in list_recent_drafts(limit=200)
        if is_review_status(record.status)
    ]
    return items[:limit]
