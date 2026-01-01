# B1-test Kickoff (Test)

## Scope
Add tests/fixtures for streaming env helpers, screenshot manager filters, and `/healthz` JSON. No production code changes.

## Start Checklist
1. `git checkout feat/browser-integration && git pull --ff-only`
2. Read `plan.md`, `tasks.json`, `session_log.md`, `B1-spec.md`, and this prompt.
3. Set `B1-test` status to `in_progress` in `tasks.json`.
4. Add START entry to `session_log.md`; commit docs (`docs: start B1-test`).
5. `git branch bi-b1-streaming-test feat/browser-integration`
6. `git worktree add wt/bi-b1-streaming-test bi-b1-streaming-test`
7. No docs/tasks/session logs from the worktree.

## Requirements
- Tests for `STREAMING_MODE`/`STREAMING_QUALITY` normalization + invalid input fallback.
- Tests for `ScreenshotManager.get_screenshots` filters (session/type/time/metadata-only).
- Mocked `/healthz` handler verifying JSON includes required keys.

## Commands (from worktree)
- `uv run ruff format --check`
- `uv run pytest tests/smoke/test_streaming.py`

## End Checklist
1. Ensure commands pass, capture outputs.
2. Commit test changes in `wt/bi-b1-streaming-test`.
3. Update `tasks.json`/`session_log.md` on `feat/browser-integration`; commit docs (`docs: finish B1-test`).
4. `git worktree remove wt/bi-b1-streaming-test`.
