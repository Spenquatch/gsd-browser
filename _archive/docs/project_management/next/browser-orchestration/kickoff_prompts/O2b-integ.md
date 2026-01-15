# Kickoff – O2b-integ (`get_run_events` tool + response modes)

## Role
Integration agent: merge code+tests, reconcile to spec, and own final green. Do not edit docs/tasks/session logs from the worktree.

## Goal
Integrate `O2b-code` + `O2b-test` and ensure behavior matches `O2b-spec`; gate with ruff/pytest and finish with `make smoke`.

## Read first
- `docs/project_management/next/browser-orchestration/plan.md`
- `docs/project_management/next/browser-orchestration/tasks.json`
- `docs/project_management/next/browser-orchestration/session_log.md`
- `docs/project_management/next/browser-orchestration/O2b-spec.md`

## Start checklist (must follow)
1. `git checkout feat/browser-orchestration && git pull --ff-only`
2. Set `O2b-integ` to `in_progress` in `tasks.json` (orchestration branch only).
3. Add START entry to `session_log.md`; commit docs (`docs: start O2b-integ`).
4. Create branch `bo-o2b-run-events-tool-integ`, then worktree: `git worktree add wt/bo-o2b-run-events-tool-integ bo-o2b-run-events-tool-integ`.
5. Do not edit docs/tasks/session_log from the worktree.

## Required commands (record output in END entry)
- `uv run ruff format --check`
- `uv run ruff check`
- `uv run pytest`
- `make smoke` (required)

## End checklist
1. Merge `bo-o2b-run-events-tool-code` and `bo-o2b-run-events-tool-test` into the integration worktree; reconcile to spec.
2. Run required commands and capture outputs.
3. Commit integration changes and fast-forward merge into `feat/browser-orchestration`.
4. Update docs on orchestration branch: mark task completed; END entry; commit (`docs: finish O2b-integ`).
5. Remove worktree `wt/bo-o2b-run-events-tool-integ`.
