# Kickoff – R3-integ (Report formatting integration)

## Role
Integration agent: merge code+tests, reconcile behavior to the spec, and make the slice green. Do not edit docs/tasks/session logs from the worktree.

## Goal
Integrate `R3-code` + `R3-test` per `R3-spec`.

## Read first
- `docs/project_management/next/real-world-sanity-harness/plan.md`
- `docs/project_management/next/real-world-sanity-harness/tasks.json`
- `docs/project_management/next/real-world-sanity-harness/session_log.md`
- `docs/project_management/next/real-world-sanity-harness/R3-spec.md`

## Start checklist (must follow)
1. `git checkout feat/real-world-sanity-harness && git pull --ff-only`
2. Set `R3-integ` to `in_progress` in `tasks.json` (orchestration branch only).
3. Add START entry to `session_log.md`; commit docs (`docs: start R3-integ`).
4. Create branch `rw-r3-report-integ`, then worktree: `git worktree add wt/rw-r3-report-integ rw-r3-report-integ`.
5. Do not edit docs/tasks/session_log from the worktree.

## Required commands (record output in END entry)
- `uv run ruff format --check`
- `uv run ruff check`
- `uv run pytest`
- `make smoke`

## End checklist
1. Run required commands and capture outputs.
2. Commit changes inside `wt/rw-r3-report-integ` (no docs edits).
3. Switch back to `feat/real-world-sanity-harness`; mark task done; add END entry; commit docs (`docs: finish R3-integ`). Fast-forward merge this integration branch into `feat/real-world-sanity-harness` only when green.
4. Remove worktree `wt/rw-r3-report-integ`.

