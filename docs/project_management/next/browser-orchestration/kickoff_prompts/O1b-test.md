# Kickoff – O1b-test (Pause gating + screenshot recording tests)

## Role
Test agent: tests/fixtures only. No production code. Do not edit docs/tasks/session logs from the worktree.

## Goal
Add tests for `O1b-spec`: pause gating behavior and screenshot-recording calls using mocks/stubs.

## Read first
- `docs/project_management/next/browser-orchestration/plan.md`
- `docs/project_management/next/browser-orchestration/tasks.json`
- `docs/project_management/next/browser-orchestration/session_log.md`
- `docs/project_management/next/browser-orchestration/O1b-spec.md`

## Start checklist (must follow)
1. `git checkout feat/browser-orchestration && git pull --ff-only`
2. Set `O1b-test` to `in_progress` in `tasks.json` (orchestration branch only).
3. Add START entry to `session_log.md`; commit docs (`docs: start O1b-test`).
4. Create branch `bo-o1b-callbacks-test`, then worktree: `git worktree add wt/bo-o1b-callbacks-test bo-o1b-callbacks-test`.
5. Do not edit docs/tasks/session_log from the worktree.

## Constraints / guardrails
- Keep tests deterministic (no real browser).
- Validate pause gating blocks between steps; validate screenshot capture is invoked and artifacts update (via mocks/stubs).

## Required commands (record output in END entry)
- `uv run ruff format --check`
- `uv run pytest gsd-browser/tests -k o1b`

## End checklist
1. Run required commands and capture outputs.
2. Commit changes inside `wt/bo-o1b-callbacks-test` (no docs edits).
3. Switch back to `feat/browser-orchestration`; mark task completed; add END entry; commit docs (`docs: finish O1b-test`). Do not merge this branch into `feat/browser-orchestration`.
4. Remove worktree `wt/bo-o1b-callbacks-test`.
