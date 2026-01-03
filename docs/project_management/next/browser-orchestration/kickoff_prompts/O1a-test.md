# Kickoff – O1a-test (Contract + final_result extraction tests)

## Role
Test agent: tests/fixtures only. No production code. Do not edit docs/tasks/session logs from the worktree.

## Goal
Add tests for `O1a-spec`: validate response JSON shape and `final_result()` extraction via mocks/stubs (no real browser).

## Read first
- `docs/project_management/next/browser-orchestration/plan.md`
- `docs/project_management/next/browser-orchestration/tasks.json`
- `docs/project_management/next/browser-orchestration/session_log.md`
- `docs/project_management/next/browser-orchestration/O1a-spec.md`

## Start checklist (must follow)
1. `git checkout feat/browser-orchestration && git pull --ff-only`
2. Set `O1a-test` to `in_progress` in `tasks.json` (orchestration branch only).
3. Add START entry to `session_log.md`; commit docs (`docs: start O1a-test`).
4. Create branch `bo-o1a-orchestrator-test`, then worktree: `git worktree add wt/bo-o1a-orchestrator-test bo-o1a-orchestrator-test`.
5. Do not edit docs/tasks/session_log from the worktree.

## Constraints / guardrails
- Tests must be fast and deterministic (no Playwright/browser dependency).
- Validate required JSON keys and bounded fields; validate `result` mapping to `final_result()` when present.
- Ensure no inline images are returned by default.

## Required commands (record output in END entry)
- `uv run ruff format --check`
- `uv run pytest gsd-browser/tests -k o1a`

## End checklist
1. Run required commands and capture outputs.
2. Commit changes inside `wt/bo-o1a-orchestrator-test` (no docs edits).
3. Switch back to `feat/browser-orchestration`; mark task completed; add END entry; commit docs (`docs: finish O1a-test`). Do not merge this branch into `feat/browser-orchestration`.
4. Remove worktree `wt/bo-o1a-orchestrator-test`.
