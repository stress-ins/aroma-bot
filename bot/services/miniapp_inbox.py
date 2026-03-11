from __future__ import annotations

from bot.services.drafts_store import DraftRecord, list_recent_drafts
from bot.services.miniapp_presenter import payload_preview


REVIEW_STATUSES = {"draft", "in_review"}
INBOX_KINDS = {"all", "content", "reels", "plan"}


def is_review_status(status: str) -> bool:
    return status.strip().lower() in REVIEW_STATUSES


def inbox_category(record: DraftRecord) -> str:
    if record.source.strip() == "/plan":
        return "plan"
    if record.kind.strip().lower() == "reels":
        return "reels"
    return "content"


def inbox_reason(record: DraftRecord) -> str:
    if record.source.strip() == "/plan":
        return "Создано из контент-плана и ждёт подтверждения."
    if record.kind.strip().lower() == "reels":
        return "Reels-сценарий и раскадровка ждут review."
    if record.status.strip().lower() == "in_review":
        return "Черновик уже в review и ждёт финального согласования."
    return "Новый draft ещё не проходил согласование."


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
        "category": inbox_category(record),
        "review_reason": inbox_reason(record),
    }


async def list_inbox_items(limit: int = 100, kind_filter: str = "all") -> list[dict[str, object]]:
    normalized_kind = kind_filter.strip().lower() or "all"
    if normalized_kind not in INBOX_KINDS:
        normalized_kind = "all"

    items = []
    for record in await list_recent_drafts(limit=200):
        if not is_review_status(record.status):
            continue
        item = serialize_inbox_item(record)
        if normalized_kind != "all" and item["category"] != normalized_kind:
            continue
        items.append(item)
    return items[:limit]
