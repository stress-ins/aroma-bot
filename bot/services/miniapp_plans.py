from __future__ import annotations

from bot.services.drafts_store import list_recent_drafts
from bot.services.plans_store import PlanRecord


async def serialize_plan(record: PlanRecord) -> dict[str, object]:
    plan_topics = {entry.get("topic", "").strip() for entry in record.entries if entry.get("topic")}
    related_drafts = [
        {
            "draft_id": draft.draft_id,
            "kind": draft.kind,
            "topic": draft.topic,
            "status": draft.status,
        }
        for draft in await list_recent_drafts(limit=200)
        if draft.source == "/plan" and draft.topic.strip() in plan_topics
    ]
    return {
        "plan_id": record.plan_id,
        "created_at": record.created_at,
        "raw_text": record.raw_text,
        "entries": record.entries,
        "status": record.status,
        "related_drafts": related_drafts,
    }
