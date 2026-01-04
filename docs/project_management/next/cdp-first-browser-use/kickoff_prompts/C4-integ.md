# Kickoff – C4-integ (CDP-first streaming adapter integration)

## Role
Integration agent: merge code+tests, reconcile behavior to the spec, and make the slice green. Do not edit docs/tasks/session logs from the worktree.

## Goal
Integrate `C4-code` + `C4-test` per `C4-spec`.

## Read first
- `docs/project_management/next/cdp-first-browser-use/plan.md`
- `docs/project_management/next/cdp-first-browser-use/tasks.json`
- `docs/project_management/next/cdp-first-browser-use/session_log.md`
- `docs/project_management/next/cdp-first-browser-use/C4-spec.md`

## Start checklist (must follow)
1. `git checkout feat/cdp-first-browser-use && git pull --ff-only`
2. Set `C4-integ` to `in_progress` in `tasks.json` (orchestration branch only).
3. Add START entry to `session_log.md`; commit docs (`docs: start C4-integ`).
4. Create branch `cf-c4-streaming-integ`, then worktree: `git worktree add wt/cf-c4-streaming-integ cf-c4-streaming-integ`.
5. Do not edit docs/tasks/session_log from the worktree.

## Required commands (record output in END entry)
- `uv run ruff format --check`
- `uv run ruff check`
- `uv run pytest`
- `make smoke`

## End checklist
1. Run required commands and capture outputs.
2. Commit changes inside `wt/cf-c4-streaming-integ` (no docs edits).
3. Switch back to `feat/cdp-first-browser-use`; mark task done; add END entry; commit docs (`docs: finish C4-integ`). Fast-forward merge this integration branch into `feat/cdp-first-browser-use` only when green.
4. Remove worktree `wt/cf-c4-streaming-integ`.

