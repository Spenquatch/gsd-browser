# Kickoff – O2b-test (`get_run_events` + mode selection tests)

## Role
Test agent: tests/fixtures only. No production code. Do not edit docs/tasks/session logs from the worktree.

## Goal
Add tests for `O2b-spec`: `get_run_events` filtering/limits and `web_eval_agent` `mode` default selection.

## Read first
- `docs/project_management/next/browser-orchestration/plan.md`
- `docs/project_management/next/browser-orchestration/tasks.json`
- `docs/project_management/next/browser-orchestration/session_log.md`
- `docs/project_management/next/browser-orchestration/O2b-spec.md`

## Start checklist (must follow)
1. `git checkout feat/browser-orchestration && git pull --ff-only`
2. Set `O2b-test` to `in_progress` in `tasks.json` (orchestration branch only).
3. Add START entry to `session_log.md`; commit docs (`docs: start O2b-test`).
4. Create branch `bo-o2b-run-events-tool-test`, then worktree: `git worktree add wt/bo-o2b-run-events-tool-test bo-o2b-run-events-tool-test`.
5. Do not edit docs/tasks/session_log from the worktree.

## Constraints / guardrails
- Cover strict limits and filtering behavior (session/type/timestamp/error as applicable).
- Cover `mode` defaults based on URL host (localhost => `dev`, else `compact`) and explicit override.

## Required commands (record output in END entry)
- `uv run ruff format --check`
- `uv run pytest gsd-browser/tests -k o2b`

## End checklist
1. Run required commands and capture outputs.
2. Commit changes inside `wt/bo-o2b-run-events-tool-test` (no docs edits).
3. Switch back to `feat/browser-orchestration`; mark task completed; add END entry; commit docs (`docs: finish O2b-test`). Do not merge this branch into `feat/browser-orchestration`.
4. Remove worktree `wt/bo-o2b-run-events-tool-test`.
