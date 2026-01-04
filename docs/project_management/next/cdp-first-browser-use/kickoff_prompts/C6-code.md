# Kickoff – C6-code (Take-control target robustness)

## Role
Code agent: production code only. No tests. Do not edit docs/tasks/session logs from the worktree.

## Goal
Implement `C6-spec`: ensure ctrl input dispatch targets the active browser-use CDP session and strengthen pause/control semantics.

## Read first
- `docs/project_management/next/cdp-first-browser-use/plan.md`
- `docs/project_management/next/cdp-first-browser-use/tasks.json`
- `docs/project_management/next/cdp-first-browser-use/session_log.md`
- `docs/project_management/next/cdp-first-browser-use/C6-spec.md`
- `docs/adr/ADR-0003-cdp-first-browser-use-integration.md`

## Start checklist (must follow)
1. `git checkout feat/cdp-first-browser-use && git pull --ff-only`
2. Set `C6-code` to `in_progress` in `tasks.json` (orchestration branch only).
3. Add START entry to `session_log.md`; commit docs (`docs: start C6-code`).
4. Create branch `cf-c6-control-target-code`, then worktree: `git worktree add wt/cf-c6-control-target-code cf-c6-control-target-code`.
5. Do not edit docs/tasks/session_log from the worktree.

## Constraints / requirements
- Maintain holder-only and paused-only acceptance rules.
- Dispatch must re-acquire focus/target when detaches happen (best effort) instead of hard failing.
- Auto-pause on take-control is default behavior unless explicitly disabled.

## Required commands (record output in END entry)
- `uv run ruff format --check`
- `uv run ruff check`

## End checklist
1. Run required commands and capture outputs.
2. Commit changes inside `wt/cf-c6-control-target-code` (no docs edits).
3. Switch back to `feat/cdp-first-browser-use`; mark task completed; add END entry; commit docs (`docs: finish C6-code`). Do not merge this branch into `feat/cdp-first-browser-use`.
4. Remove worktree `wt/cf-c6-control-target-code`.

