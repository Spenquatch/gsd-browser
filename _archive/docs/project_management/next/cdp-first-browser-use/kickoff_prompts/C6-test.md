# Kickoff – C6-test (Take-control target robustness tests)

## Role
Test agent: tests only. No production code changes. Do not edit docs/tasks/session logs from the worktree.

## Goal
Add unit tests for `C6-spec`:
- holder-only and paused-only gating is preserved
- target re-acquisition occurs when dispatch errors simulate detaches
- resume behavior does not replay stale buffered inputs

## Read first
- `docs/project_management/next/cdp-first-browser-use/plan.md`
- `docs/project_management/next/cdp-first-browser-use/tasks.json`
- `docs/project_management/next/cdp-first-browser-use/session_log.md`
- `docs/project_management/next/cdp-first-browser-use/C6-spec.md`

## Start checklist (must follow)
1. `git checkout feat/cdp-first-browser-use && git pull --ff-only`
2. Set `C6-test` to `in_progress` in `tasks.json` (orchestration branch only).
3. Add START entry to `session_log.md`; commit docs (`docs: start C6-test`).
4. Create branch `cf-c6-control-target-test`, then worktree: `git worktree add wt/cf-c6-control-target-test cf-c6-control-target-test`.
5. Do not edit docs/tasks/session_log from the worktree.

## Required commands (record output in END entry)
- `uv run ruff format --check`
- `uv run pytest gsd-browser/tests -k c6`

## End checklist
1. Run required commands and capture outputs.
2. Commit changes inside `wt/cf-c6-control-target-test` (no docs edits).
3. Switch back to `feat/cdp-first-browser-use`; mark task completed; add END entry; commit docs (`docs: finish C6-test`). Do not merge this branch into `feat/cdp-first-browser-use`.
4. Remove worktree `wt/cf-c6-control-target-test`.

