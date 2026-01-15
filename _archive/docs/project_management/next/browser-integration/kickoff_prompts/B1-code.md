# B1-code Kickoff (Code)

## Scope
Implement the streaming core described in `B1-spec.md`. Production code only: env helpers, CDP frame pipeline, `/healthz`, screenshot manager integration, logging. No tests.

## Start Checklist
1. `git checkout feat/browser-integration && git pull --ff-only`
2. Read `plan.md`, `tasks.json`, `session_log.md`, `B1-spec.md`, and this prompt.
3. Set `B1-code` status to `in_progress` in `tasks.json`.
4. Add a START entry to `session_log.md`; commit docs (`docs: start B1-code`).
5. `git branch bi-b1-streaming-code feat/browser-integration`
6. `git worktree add wt/bi-b1-streaming-code bi-b1-streaming-code`
7. Do **not** edit docs/tasks/session log from the worktree.

## Requirements
- Port env toggles (`STREAMING_MODE`, `STREAMING_QUALITY`) and integrate them with the CLI/config system.
- Implement CDP screencast start/stop, frame queueing, metadata, screenshot sampling hook, and `/healthz` metrics.
- Maintain screenshot fallback path (legacy `browser_update`).
- Emit structured logs per spec.
- Touch only production modules (no tests/docs).

## Commands (must run inside the worktree before committing)
- `uv run ruff format --check`
- `uv run ruff check`

## End Checklist
1. Ensure required commands pass and capture outputs for the END log entry.
2. Commit production changes inside `wt/bi-b1-streaming-code` (no docs/tasks/log updates).
3. Checkout `feat/browser-integration`; update `tasks.json` (status `done`) and `session_log.md` with the END entry; commit docs (`docs: finish B1-code`).
4. `git worktree remove wt/bi-b1-streaming-code`.
