# Kickoff – O3c-test (Wiring sanity tests)

## Role
Test agent: tests/fixtures only. No production code. Do not edit docs/tasks/session logs from the worktree.

## Goal
Keep this small: add any minimal tests needed for client/server wiring assumptions; primary server-side validation is covered by O3a/O3b.

## Read first
- `docs/project_management/next/browser-orchestration/plan.md`
- `docs/project_management/next/browser-orchestration/tasks.json`
- `docs/project_management/next/browser-orchestration/session_log.md`
- `docs/project_management/next/browser-orchestration/O3c-spec.md`

## Start checklist (must follow)
1. `git checkout feat/browser-orchestration && git pull --ff-only`
2. Set `O3c-test` to `in_progress` in `tasks.json` (orchestration branch only).
3. Add START entry to `session_log.md`; commit docs (`docs: start O3c-test`).
4. Create branch `bo-o3c-dashboard-input-test`, then worktree: `git worktree add wt/bo-o3c-dashboard-input-test bo-o3c-dashboard-input-test`.
5. Do not edit docs/tasks/session_log from the worktree.

## Constraints / guardrails
- Keep tests minimal, fast, and deterministic.
- Do not duplicate O3a/O3b server validation coverage; only cover O3c-specific assumptions.

## Required commands (record output in END entry)
- `uv run ruff format --check`
- `uv run pytest gsd-browser/tests -k o3c`

## End checklist
1. Run required commands and capture outputs.
2. Commit changes inside `wt/bo-o3c-dashboard-input-test` (no docs edits).
3. Switch back to `feat/browser-orchestration`; mark task completed; add END entry; commit docs (`docs: finish O3c-test`). Do not merge this branch into `feat/browser-orchestration`.
4. Remove worktree `wt/bo-o3c-dashboard-input-test`.
