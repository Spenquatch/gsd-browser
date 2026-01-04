# Kickoff – R3-code (Report formatting)

## Role
Code agent: production code only. No tests. Do not edit docs/tasks/session logs from the worktree.

## Goal
Implement `R3-spec`: emit stable `summary.json` + PR-friendly `report.md` (errors-first, bounded).

## Read first
- `docs/project_management/next/real-world-sanity-harness/plan.md`
- `docs/project_management/next/real-world-sanity-harness/tasks.json`
- `docs/project_management/next/real-world-sanity-harness/session_log.md`
- `docs/project_management/next/real-world-sanity-harness/R3-spec.md`

## Start checklist (must follow)
1. `git checkout feat/real-world-sanity-harness && git pull --ff-only`
2. Set `R3-code` to `in_progress` in `tasks.json` (orchestration branch only).
3. Add START entry to `session_log.md`; commit docs (`docs: start R3-code`).
4. Create branch `rw-r3-report-code`, then worktree: `git worktree add wt/rw-r3-report-code rw-r3-report-code`.
5. Do not edit docs/tasks/session_log from the worktree.

## Constraints / requirements
- Report must be compact and link artifacts via relative paths.
- Avoid dumping large logs into Markdown; store large details in JSON files.

## Required commands (record output in END entry)
- `uv run ruff format --check`
- `uv run ruff check`

## End checklist
1. Run required commands and capture outputs.
2. Commit changes inside `wt/rw-r3-report-code` (no docs edits).
3. Switch back to `feat/real-world-sanity-harness`; mark task completed; add END entry; commit docs (`docs: finish R3-code`). Do not merge this branch into `feat/real-world-sanity-harness`.
4. Remove worktree `wt/rw-r3-report-code`.

