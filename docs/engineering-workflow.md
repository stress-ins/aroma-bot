# Engineering Workflow

## Storage Boundaries

- `Drafts` and `Plans` use SQLite as the runtime source of truth.
- JSON files under `data/` are allowed only for handbook seed/import flows and offline utilities.
- If a runtime behavior needs persistence, prefer `db/models.py` + Alembic migration + service layer, not a new JSON path.

## PR Boundaries

- Prefer `behavior/product` PRs and `coverage/alignment` PRs as separate units of work.
- A behavior PR may include only the minimum test changes needed to validate that behavior.
- A coverage/alignment PR should not silently include prompt, UX, persistence, or handler changes unless they are required to unbreak the test suite.
- If a branch starts as `test alignment` and grows into product changes, split it or rename the PR so the scope stays honest.

## Miniapp Shared Core

- Shared miniapp helpers live in focused modules under `miniapp/static/js/`.
- Keep `miniapp/static/app.js` as orchestration glue, state wiring, and window bridge only.
- When moving logic out of `app.js`, prefer extracting reusable helpers first: UI feedback, request helpers, pending-draft lifecycle, and navigation coordination.
