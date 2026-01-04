# Kickoff – R1-test (Harness runner + scenario registry tests)

## Role
Test agent: tests only. No production code changes. Do not edit docs/tasks/session logs from the worktree.

## Goal
Add unit tests for `R1-spec`:
- scenario selection by id
- output tree creation (without running real web_eval_agent)

## Read first
- `docs/project_management/next/real-world-sanity-harness/plan.md`
- `docs/project_management/next/real-world-sanity-harness/tasks.json`
- `docs/project_management/next/real-world-sanity-harness/session_log.md`
- `docs/project_management/next/real-world-sanity-harness/R1-spec.md`

## Start checklist (must follow)
1. `git checkout feat/real-world-sanity-harness && git pull --ff-only`
2. Set `R1-test` to `in_progress` in `tasks.json` (orchestration branch only).
3. Add START entry to `session_log.md`; commit docs (`docs: start R1-test`).
4. Create branch `rw-r1-harness-test`, then worktree: `git worktree add wt/rw-r1-harness-test rw-r1-harness-test`.
5. Do not edit docs/tasks/session_log from the worktree.

## Constraints / requirements
- Tests must not hit real websites; stub/mocks only.

## Required commands (record output in END entry)
- `uv run ruff format --check`
- `uv run pytest gsd-browser/tests -k r1`

## End checklist
1. Run required commands and capture outputs.
2. Commit changes inside `wt/rw-r1-harness-test` (no docs edits).
3. Switch back to `feat/real-world-sanity-harness`; mark task completed; add END entry; commit docs (`docs: finish R1-test`). Do not merge this branch into `feat/real-world-sanity-harness`.
4. Remove worktree `wt/rw-r1-harness-test`.

