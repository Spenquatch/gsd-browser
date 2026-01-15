# Kickoff – C3-code (Step screenshots guarantee)

## Role
Code agent: production code only. No tests. Do not edit docs/tasks/session logs from the worktree.

## Goal
Implement `C3-spec`: guarantee step screenshots via `BrowserStateSummary` primary path + browser-use “current page” fallback, with bounds and metadata.

## Read first
- `docs/project_management/next/cdp-first-browser-use/plan.md`
- `docs/project_management/next/cdp-first-browser-use/tasks.json`
- `docs/project_management/next/cdp-first-browser-use/session_log.md`
- `docs/project_management/next/cdp-first-browser-use/C3-spec.md`
- `docs/adr/ADR-0003-cdp-first-browser-use-integration.md`

## Start checklist (must follow)
1. `git checkout feat/cdp-first-browser-use && git pull --ff-only`
2. Set `C3-code` to `in_progress` in `tasks.json` (orchestration branch only).
3. Add START entry to `session_log.md`; commit docs (`docs: start C3-code`).
4. Create branch `cf-c3-screenshots-code`, then worktree: `git worktree add wt/cf-c3-screenshots-code cf-c3-screenshots-code`.
5. Do not edit docs/tasks/session_log from the worktree.

## Constraints / requirements
- Do not rely on `BrowserStateSummary.screenshot` always being present.
- Fallback capture must not crash the agent run; handle errors and keep going.
- Enforce per-session caps; do not allow unbounded screenshot growth.

## Required commands (record output in END entry)
- `uv run ruff format --check`
- `uv run ruff check`

## End checklist
1. Run required commands and capture outputs.
2. Commit changes inside `wt/cf-c3-screenshots-code` (no docs edits).
3. Switch back to `feat/cdp-first-browser-use`; mark task completed; add END entry; commit docs (`docs: finish C3-code`). Do not merge this branch into `feat/cdp-first-browser-use`.
4. Remove worktree `wt/cf-c3-screenshots-code`.

