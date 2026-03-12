# Data Storage Architecture

## Runtime source of truth

- `Drafts` are stored in SQLite via `db/models.py` -> `DraftModel`.
- `Plans` are stored in SQLite via `db/models.py` -> `PlanModel`.
- Runtime access goes through:
  - `bot/services/drafts_store.py`
  - `bot/services/plans_store.py`
  - `db/session.py`

## What JSON is still used for

- JSON files in `data/` are seed/import inputs for reference cards.
- JSON files in `scripts/` are patch/import payloads for offline maintenance scripts.
- JSON fields inside SQLite rows are part of the database schema, not a separate file-based store.

## Rules

- Do not add new file-based JSON storage for `Drafts` or `Plans`.
- If runtime data shape changes, update SQLAlchemy models and Alembic migrations.
- If reference seed data changes, update the seed/import JSON and the scripts that ingest it into the database.

## Practical guideline

- `SQLite/DB` answers: "what the app currently knows"
- `seed/import JSON` answers: "what we can preload or patch into the DB"
