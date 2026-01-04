# Kickoff – C3-test (Step screenshots guarantee tests)

## Role
Test agent: tests only. No production code changes. Do not edit docs/tasks/session logs from the worktree.

## Goal
Add unit tests for `C3-spec`:
- fallback capture path is attempted when summary screenshot is missing
- per-session screenshot cap/eviction works
- metadata is present

## Read first
- `docs/project_management/next/cdp-first-browser-use/plan.md`
- `docs/project_management/next/cdp-first-browser-use/tasks.json`
- `docs/project_management/next/cdp-first-browser-use/session_log.md`
- `docs/project_management/next/cdp-first-browser-use/C3-spec.md`

## Start checklist (must follow)
1. `git checkout feat/cdp-first-browser-use && git pull --ff-only`
2. Set `C3-test` to `in_progress` in `tasks.json` (orchestration branch only).
3. Add START entry to `session_log.md`; commit docs (`docs: start C3-test`).
4. Create branch `cf-c3-screenshots-test`, then worktree: `git worktree add wt/cf-c3-screenshots-test cf-c3-screenshots-test`.
5. Do not edit docs/tasks/session_log from the worktree.

## Required commands (record output in END entry)
- `uv run ruff format --check`
- `uv run pytest gsd-browser/tests -k c3`

## End checklist
1. Run required commands and capture outputs.
2. Commit changes inside `wt/cf-c3-screenshots-test` (no docs edits).
3. Switch back to `feat/cdp-first-browser-use`; mark task completed; add END entry; commit docs (`docs: finish C3-test`). Do not merge this branch into `feat/cdp-first-browser-use`.
4. Remove worktree `wt/cf-c3-screenshots-test`.

