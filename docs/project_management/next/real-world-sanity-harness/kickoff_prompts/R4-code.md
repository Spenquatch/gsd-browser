# Kickoff – R4-code (Quality gates ergonomics)

## Role
Code agent: production code only. No tests. Do not edit docs/tasks/session logs from the worktree.

## Goal
Implement the *code* portion of `R4-spec`:
- optional ergonomics like a Makefile target to run the harness
- keep the harness opt-in and out of CI

## Read first
- `docs/project_management/next/real-world-sanity-harness/plan.md`
- `docs/project_management/next/real-world-sanity-harness/tasks.json`
- `docs/project_management/next/real-world-sanity-harness/session_log.md`
- `docs/project_management/next/real-world-sanity-harness/R4-spec.md`

## Start checklist (must follow)
1. `git checkout feat/real-world-sanity-harness && git pull --ff-only`
2. Set `R4-code` to `in_progress` in `tasks.json` (orchestration branch only).
3. Add START entry to `session_log.md`; commit docs (`docs: start R4-code`).
4. Create branch `rw-r4-gates-code`, then worktree: `git worktree add wt/rw-r4-gates-code rw-r4-gates-code`.
5. Do not edit docs/tasks/session_log from the worktree.

## Constraints / requirements
- Do not add this harness to default CI. Keep it opt-in.
- Any helper command must make it clear that it requires credentials + internet.

## Required commands (record output in END entry)
- `uv run ruff format --check`
- `uv run ruff check`

## End checklist
1. Run required commands and capture outputs.
2. Commit changes inside `wt/rw-r4-gates-code` (no docs edits).
3. Switch back to `feat/real-world-sanity-harness`; mark task completed; add END entry; commit docs (`docs: finish R4-code`). Do not merge this branch into `feat/real-world-sanity-harness`.
4. Remove worktree `wt/rw-r4-gates-code`.

