# Kickoff – C4-test (CDP-first streaming adapter tests)

## Role
Test agent: tests only. No production code changes. Do not edit docs/tasks/session logs from the worktree.

## Goal
Add unit tests for `C4-spec`:
- start/stop lifecycle does not leak tasks
- sampling and backpressure counters behave as expected
- “CDP unavailable” fallback keeps the run functional (via stubs)

## Read first
- `docs/project_management/next/cdp-first-browser-use/plan.md`
- `docs/project_management/next/cdp-first-browser-use/tasks.json`
- `docs/project_management/next/cdp-first-browser-use/session_log.md`
- `docs/project_management/next/cdp-first-browser-use/C4-spec.md`

## Start checklist (must follow)
1. `git checkout feat/cdp-first-browser-use && git pull --ff-only`
2. Set `C4-test` to `in_progress` in `tasks.json` (orchestration branch only).
3. Add START entry to `session_log.md`; commit docs (`docs: start C4-test`).
4. Create branch `cf-c4-streaming-test`, then worktree: `git worktree add wt/cf-c4-streaming-test cf-c4-streaming-test`.
5. Do not edit docs/tasks/session_log from the worktree.

## Required commands (record output in END entry)
- `uv run ruff format --check`
- `uv run pytest gsd-browser/tests -k c4`

## End checklist
1. Run required commands and capture outputs.
2. Commit changes inside `wt/cf-c4-streaming-test` (no docs edits).
3. Switch back to `feat/cdp-first-browser-use`; mark task completed; add END entry; commit docs (`docs: finish C4-test`). Do not merge this branch into `feat/cdp-first-browser-use`.
4. Remove worktree `wt/cf-c4-streaming-test`.

