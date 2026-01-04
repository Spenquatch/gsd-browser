# Kickoff – R4-test (Quality gates tests)

## Role
Test agent: tests only. No production code changes. Do not edit docs/tasks/session logs from the worktree.

## Goal
Add any tests required by `R4-spec` (only if code changes introduce behavior needing coverage).

Most of R4 is documentation and should be implemented on the orchestration branch after integration; keep tests minimal.

## Read first
- `docs/project_management/next/real-world-sanity-harness/plan.md`
- `docs/project_management/next/real-world-sanity-harness/tasks.json`
- `docs/project_management/next/real-world-sanity-harness/session_log.md`
- `docs/project_management/next/real-world-sanity-harness/R4-spec.md`

## Start checklist (must follow)
1. `git checkout feat/real-world-sanity-harness && git pull --ff-only`
2. Set `R4-test` to `in_progress` in `tasks.json` (orchestration branch only).
3. Add START entry to `session_log.md`; commit docs (`docs: start R4-test`).
4. Create branch `rw-r4-gates-test`, then worktree: `git worktree add wt/rw-r4-gates-test rw-r4-gates-test`.
5. Do not edit docs/tasks/session_log from the worktree.

## Required commands (record output in END entry)
- `uv run ruff format --check`
- `uv run pytest gsd-browser/tests -k r4`

## End checklist
1. Run required commands and capture outputs.
2. Commit changes inside `wt/rw-r4-gates-test` (no docs edits).
3. Switch back to `feat/real-world-sanity-harness`; mark task completed; add END entry; commit docs (`docs: finish R4-test`). Do not merge this branch into `feat/real-world-sanity-harness`.
4. Remove worktree `wt/rw-r4-gates-test`.

