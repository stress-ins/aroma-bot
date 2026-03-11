from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


_PLANS_FILE = Path(__file__).parent.parent.parent / "data" / "plans.json"


@dataclass
class PlanRecord:
    plan_id: str
    created_at: str
    raw_text: str
    entries: list[dict[str, str]]


def _ensure_store() -> None:
    _PLANS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not _PLANS_FILE.exists():
        _PLANS_FILE.write_text("[]", encoding="utf-8")


def _load_records() -> list[PlanRecord]:
    _ensure_store()
    raw = json.loads(_PLANS_FILE.read_text(encoding="utf-8"))
    records: list[PlanRecord] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        entries = item.get("entries", [])
        records.append(
            PlanRecord(
                plan_id=str(item.get("plan_id", "")),
                created_at=str(item.get("created_at", "")),
                raw_text=str(item.get("raw_text", "")),
                entries=[dict(entry) for entry in entries if isinstance(entry, dict)],
            )
        )
    return records


def _save_records(records: list[PlanRecord]) -> None:
    _ensure_store()
    _PLANS_FILE.write_text(
        json.dumps([asdict(record) for record in records], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def save_plan(raw_text: str, entries: list[dict[str, str]]) -> PlanRecord:
    records = _load_records()
    record = PlanRecord(
        plan_id=datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"),
        created_at=datetime.now(timezone.utc).isoformat(),
        raw_text=raw_text.strip(),
        entries=entries,
    )
    records.insert(0, record)
    _save_records(records[:100])
    return record


def list_recent_plans(limit: int = 10) -> list[PlanRecord]:
    return _load_records()[:limit]


def get_plan(plan_id: str) -> PlanRecord | None:
    for record in _load_records():
        if record.plan_id == plan_id:
            return record
    return None
