# Kickoff – O2a-integ (Run event store + capture pipeline)

## Role
Integration agent: merge code+tests, reconcile to spec, and own final green. Do not edit docs/tasks/session logs from the worktree.

## Goal
Integrate `O2a-code` + `O2a-test` and ensure behavior matches `O2a-spec`; gate with ruff/pytest and finish with `make smoke`.

## Read first
- `docs/project_management/next/browser-orchestration/plan.md`
- `docs/project_management/next/browser-orchestration/tasks.json`
- `docs/project_management/next/browser-orchestration/session_log.md`
- `docs/project_management/next/browser-orchestration/O2a-spec.md`

## Start checklist (must follow)
1. `git checkout feat/browser-orchestration && git pull --ff-only`
2. Set `O2a-integ` to `in_progress` in `tasks.json` (orchestration branch only).
3. Add START entry to `session_log.md`; commit docs (`docs: start O2a-integ`).
4. Create branch `bo-o2a-events-store-integ`, then worktree: `git worktree add wt/bo-o2a-events-store-integ bo-o2a-events-store-integ`.
5. Do not edit docs/tasks/session_log from the worktree.

## Required commands (record output in END entry)
- `uv run ruff format --check`
- `uv run ruff check`
- `uv run pytest`
- `make smoke` (required)

## End checklist
1. Merge `bo-o2a-events-store-code` and `bo-o2a-events-store-test` into the integration worktree; reconcile to spec.
2. Run required commands and capture outputs.
3. Commit integration changes and fast-forward merge into `feat/browser-orchestration`.
4. Update docs on orchestration branch: mark task completed; END entry; commit (`docs: finish O2a-integ`).
5. Remove worktree `wt/bo-o2a-events-store-integ`.
