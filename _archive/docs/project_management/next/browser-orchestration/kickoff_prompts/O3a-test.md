# Kickoff – O3a-test (Input gating + rate limit tests)

## Role
Test agent: tests/fixtures only. No production code. Do not edit docs/tasks/session logs from the worktree.

## Goal
Add tests for `O3a-spec`: holder-only gating, paused-only gating, rate limiting, and payload validation (no real browser required).

## Read first
- `docs/project_management/next/browser-orchestration/plan.md`
- `docs/project_management/next/browser-orchestration/tasks.json`
- `docs/project_management/next/browser-orchestration/session_log.md`
- `docs/project_management/next/browser-orchestration/O3a-spec.md`

## Start checklist (must follow)
1. `git checkout feat/browser-orchestration && git pull --ff-only`
2. Set `O3a-test` to `in_progress` in `tasks.json` (orchestration branch only).
3. Add START entry to `session_log.md`; commit docs (`docs: start O3a-test`).
4. Create branch `bo-o3a-input-api-test`, then worktree: `git worktree add wt/bo-o3a-input-api-test bo-o3a-input-api-test`.
5. Do not edit docs/tasks/session_log from the worktree.

## Constraints / guardrails
- Unit tests only (no live browser).
- Validate rejects are correctly classified (non-holder, not-paused, invalid payload) and that rate limiting triggers/logs as expected.

## Required commands (record output in END entry)
- `uv run ruff format --check`
- `uv run pytest gsd-browser/tests -k o3a`

## End checklist
1. Run required commands and capture outputs.
2. Commit changes inside `wt/bo-o3a-input-api-test` (no docs edits).
3. Switch back to `feat/browser-orchestration`; mark task completed; add END entry; commit docs (`docs: finish O3a-test`). Do not merge this branch into `feat/browser-orchestration`.
4. Remove worktree `wt/bo-o3a-input-api-test`.
