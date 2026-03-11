from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


_DRAFTS_FILE = Path(__file__).parent.parent.parent / "data" / "drafts.json"


@dataclass
class DraftRecord:
    draft_id: str
    kind: str
    topic: str
    source: str
    created_at: str
    status: str
    feedback: str
    payload: dict[str, Any]


def _ensure_store() -> None:
    _DRAFTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not _DRAFTS_FILE.exists():
        _DRAFTS_FILE.write_text("[]", encoding="utf-8")


def _load_records() -> list[DraftRecord]:
    _ensure_store()
    raw = json.loads(_DRAFTS_FILE.read_text(encoding="utf-8"))
    records: list[DraftRecord] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        records.append(
            DraftRecord(
                draft_id=str(item.get("draft_id", "")),
                kind=str(item.get("kind", "")),
                topic=str(item.get("topic", "")),
                source=str(item.get("source", "")),
                created_at=str(item.get("created_at", "")),
                status=str(item.get("status", "draft")),
                feedback=str(item.get("feedback", "")),
                payload=dict(item.get("payload", {})),
            )
        )
    return records


def _save_records(records: list[DraftRecord]) -> None:
    _ensure_store()
    data = [asdict(record) for record in records]
    _DRAFTS_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def save_draft(kind: str, topic: str, source: str, payload: dict[str, Any]) -> DraftRecord:
    records = _load_records()
    record = DraftRecord(
        draft_id=uuid4().hex[:8],
        kind=kind,
        topic=topic.strip(),
        source=source.strip(),
        created_at=datetime.now(timezone.utc).isoformat(),
        status="draft",
        feedback="",
        payload=payload,
    )
    records.insert(0, record)
    _save_records(records[:200])
    return record


def list_recent_drafts(limit: int = 10, kind: str | None = None) -> list[DraftRecord]:
    records = _load_records()
    if kind:
        records = [record for record in records if record.kind == kind]
    return records[:limit]


def get_draft(draft_id: str) -> DraftRecord | None:
    for record in _load_records():
        if record.draft_id == draft_id:
            return record
    return None


def update_draft(
    draft_id: str,
    *,
    topic: str | None = None,
    status: str | None = None,
    feedback: str | None = None,
    payload: dict[str, Any] | None = None,
) -> DraftRecord | None:
    records = _load_records()
    updated: DraftRecord | None = None
    for idx, record in enumerate(records):
        if record.draft_id != draft_id:
            continue
        updated = DraftRecord(
            draft_id=record.draft_id,
            kind=record.kind,
            topic=topic if topic is not None else record.topic,
            source=record.source,
            created_at=record.created_at,
            status=status if status is not None else record.status,
            feedback=feedback if feedback is not None else record.feedback,
            payload=payload if payload is not None else record.payload,
        )
        records[idx] = updated
        break
    if updated:
        _save_records(records)
    return updated
