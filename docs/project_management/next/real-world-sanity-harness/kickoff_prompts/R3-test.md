# Kickoff – R3-test (Report formatting tests)

## Role
Test agent: tests only. No production code changes. Do not edit docs/tasks/session logs from the worktree.

## Goal
Add unit tests for `R3-spec`:
- Markdown rendering for a fixed fake `summary.json` payload
- summary schema shape/bounds

## Read first
- `docs/project_management/next/real-world-sanity-harness/plan.md`
- `docs/project_management/next/real-world-sanity-harness/tasks.json`
- `docs/project_management/next/real-world-sanity-harness/session_log.md`
- `docs/project_management/next/real-world-sanity-harness/R3-spec.md`

## Start checklist (must follow)
1. `git checkout feat/real-world-sanity-harness && git pull --ff-only`
2. Set `R3-test` to `in_progress` in `tasks.json` (orchestration branch only).
3. Add START entry to `session_log.md`; commit docs (`docs: start R3-test`).
4. Create branch `rw-r3-report-test`, then worktree: `git worktree add wt/rw-r3-report-test rw-r3-report-test`.
5. Do not edit docs/tasks/session_log from the worktree.

## Required commands (record output in END entry)
- `uv run ruff format --check`
- `uv run pytest gsd-browser/tests -k r3`

## End checklist
1. Run required commands and capture outputs.
2. Commit changes inside `wt/rw-r3-report-test` (no docs edits).
3. Switch back to `feat/real-world-sanity-harness`; mark task completed; add END entry; commit docs (`docs: finish R3-test`). Do not merge this branch into `feat/real-world-sanity-harness`.
4. Remove worktree `wt/rw-r3-report-test`.

