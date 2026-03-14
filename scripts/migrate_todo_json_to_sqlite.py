#!/usr/bin/env python3
"""One-time data migration: import existing data/todo.json items into SQLite todos table.

Run AFTER alembic upgrade head:
    .venv/bin/python scripts/migrate_todo_json_to_sqlite.py
"""
from __future__ import annotations

import asyncio
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.models import TodoModel  # noqa: E402
from db.session import AsyncSessionLocal  # noqa: E402

_TODO_PATH = Path(__file__).parent.parent / "data" / "todo.json"


async def main() -> None:
    if not _TODO_PATH.exists():
        print("data/todo.json not found — nothing to migrate.")
        return

    items = json.loads(_TODO_PATH.read_text(encoding="utf-8"))
    if not items:
        print("data/todo.json is empty — nothing to migrate.")
        return

    async with AsyncSessionLocal() as session:
        for item in items:
            todo = TodoModel(
                todo_id=item.get("id") or str(uuid.uuid4()),
                text=item.get("text", "").strip(),
            )
            session.add(todo)
        await session.commit()

    print(f"Migrated {len(items)} todo item(s) from data/todo.json to SQLite.")
    _TODO_PATH.rename(_TODO_PATH.with_suffix(".json.bak"))
    print(f"Renamed data/todo.json → data/todo.json.bak (backup)")


if __name__ == "__main__":
    asyncio.run(main())
