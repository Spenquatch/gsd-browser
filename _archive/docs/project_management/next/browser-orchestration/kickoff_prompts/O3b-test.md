# Kickoff – O3b-test (CDP dispatch mapping tests)

## Role
Test agent: tests/fixtures only. No production code. Do not edit docs/tasks/session logs from the worktree.

## Goal
Add tests for `O3b-spec`: CDP dispatch parameter mapping and Enter/type semantics using mocked CDP clients.

## Read first
- `docs/project_management/next/browser-orchestration/plan.md`
- `docs/project_management/next/browser-orchestration/tasks.json`
- `docs/project_management/next/browser-orchestration/session_log.md`
- `docs/project_management/next/browser-orchestration/O3b-spec.md`

## Start checklist (must follow)
1. `git checkout feat/browser-orchestration && git pull --ff-only`
2. Set `O3b-test` to `in_progress` in `tasks.json` (orchestration branch only).
3. Add START entry to `session_log.md`; commit docs (`docs: start O3b-test`).
4. Create branch `bo-o3b-cdp-dispatch-test`, then worktree: `git worktree add wt/bo-o3b-cdp-dispatch-test bo-o3b-cdp-dispatch-test`.
5. Do not edit docs/tasks/session_log from the worktree.

## Constraints / guardrails
- Mock CDP client; no real browser.
- Validate correct dispatch calls for click/wheel/keys/typing, including a reliable Enter sequence and modifier mapping.

## Required commands (record output in END entry)
- `uv run ruff format --check`
- `uv run pytest gsd-browser/tests -k o3b`

## End checklist
1. Run required commands and capture outputs.
2. Commit changes inside `wt/bo-o3b-cdp-dispatch-test` (no docs edits).
3. Switch back to `feat/browser-orchestration`; mark task completed; add END entry; commit docs (`docs: finish O3b-test`). Do not merge this branch into `feat/browser-orchestration`.
4. Remove worktree `wt/bo-o3b-cdp-dispatch-test`.
