# Kickoff – C1-test (Lifecycle + budgets + status mapping tests)

## Role
Test agent: tests only. No production code changes. Do not edit docs/tasks/session logs from the worktree.

## Goal
Add unit tests for `C1-spec`:
- status mapping table
- timeout/cancellation behavior produces actionable failure JSON

## Read first
- `docs/project_management/next/cdp-first-browser-use/plan.md`
- `docs/project_management/next/cdp-first-browser-use/tasks.json`
- `docs/project_management/next/cdp-first-browser-use/session_log.md`
- `docs/project_management/next/cdp-first-browser-use/C1-spec.md`

## Start checklist (must follow)
1. `git checkout feat/cdp-first-browser-use && git pull --ff-only`
2. Set `C1-test` to `in_progress` in `tasks.json` (orchestration branch only).
3. Add START entry to `session_log.md`; commit docs (`docs: start C1-test`).
4. Create branch `cf-c1-lifecycle-test`, then worktree: `git worktree add wt/cf-c1-lifecycle-test cf-c1-lifecycle-test`.
5. Do not edit docs/tasks/session_log from the worktree.

## Constraints / requirements
- Use stubs/mocks; do not make real browser/network calls.
- Prefer tests in `gsd-browser/tests/mcp/` alongside existing `web_eval_agent` contract tests.

## Required commands (record output in END entry)
- `uv run ruff format --check`
- `uv run pytest gsd-browser/tests -k c1`

## End checklist
1. Run required commands and capture outputs.
2. Commit changes inside `wt/cf-c1-lifecycle-test` (no docs edits).
3. Switch back to `feat/cdp-first-browser-use`; mark task completed; add END entry; commit docs (`docs: finish C1-test`). Do not merge this branch into `feat/cdp-first-browser-use`.
4. Remove worktree `wt/cf-c1-lifecycle-test`.

