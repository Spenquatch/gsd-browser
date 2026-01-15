# Kickoff – O2a-test (Event store limits + truncation tests)

## Role
Test agent: tests/fixtures only. No production code. Do not edit docs/tasks/session logs from the worktree.

## Goal
Add tests for `O2a-spec`: event store limits, truncation, and basic per-session/type behavior.

## Read first
- `docs/project_management/next/browser-orchestration/plan.md`
- `docs/project_management/next/browser-orchestration/tasks.json`
- `docs/project_management/next/browser-orchestration/session_log.md`
- `docs/project_management/next/browser-orchestration/O2a-spec.md`

## Start checklist (must follow)
1. `git checkout feat/browser-orchestration && git pull --ff-only`
2. Set `O2a-test` to `in_progress` in `tasks.json` (orchestration branch only).
3. Add START entry to `session_log.md`; commit docs (`docs: start O2a-test`).
4. Create branch `bo-o2a-events-store-test`, then worktree: `git worktree add wt/bo-o2a-events-store-test bo-o2a-events-store-test`.
5. Do not edit docs/tasks/session_log from the worktree.

## Constraints / guardrails
- Prefer unit tests with injected events (no browser/Playwright requirements).
- Validate limits and truncation deterministically; keep tests small and fast.

## Required commands (record output in END entry)
- `uv run ruff format --check`
- `uv run pytest gsd-browser/tests -k o2a`

## End checklist
1. Run required commands and capture outputs.
2. Commit changes inside `wt/bo-o2a-events-store-test` (no docs edits).
3. Switch back to `feat/browser-orchestration`; mark task completed; add END entry; commit docs (`docs: finish O2a-test`). Do not merge this branch into `feat/browser-orchestration`.
4. Remove worktree `wt/bo-o2a-events-store-test`.
