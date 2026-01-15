# Kickoff – O3c-code (Dashboard input capture wiring + verify steps)

## Role
Code agent: production dashboard assets only. No tests. Do not edit docs/tasks/session logs from the worktree.

## Goal
Implement `O3c-spec`: update dashboard JS to capture pointer/keyboard events and emit them to `/ctrl`, plus document minimal manual verification steps (done on the orchestration branch, not the worktree).

## Read first
- `docs/project_management/next/browser-orchestration/plan.md`
- `docs/project_management/next/browser-orchestration/tasks.json`
- `docs/project_management/next/browser-orchestration/session_log.md`
- `docs/project_management/next/browser-orchestration/O3c-spec.md`

## Start checklist (must follow)
1. `git checkout feat/browser-orchestration && git pull --ff-only`
2. Set `O3c-code` to `in_progress` in `tasks.json` (orchestration branch only).
3. Add START entry to `session_log.md`; commit docs (`docs: start O3c-code`).
4. Create branch `bo-o3c-dashboard-input-code`, then worktree: `git worktree add wt/bo-o3c-dashboard-input-code bo-o3c-dashboard-input-code`.
5. Do not edit docs/tasks/session_log from the worktree.

## Constraints / guardrails
- Client-side guard: emit input only when holder is active and paused; server remains source of truth (do not rely on client checks for security).
- Capture pointer (click/move/wheel) over the rendered surface and keyboard events when control is held.
- Manual verification steps must be concise and reproducible (take control → click/type incl Enter → release → resume); add them on `feat/browser-orchestration` after the worktree commit.

## Required commands (record output in END entry)
- `uv run ruff format --check`
- `uv run ruff check`

## End checklist
1. Run required commands and capture outputs.
2. Commit dashboard changes inside `wt/bo-o3c-dashboard-input-code` (no docs edits).
3. Switch back to `feat/browser-orchestration`; add the manual verification steps per `O3c-spec.md`; mark task completed; add END entry; commit docs (`docs: finish O3c-code`). Do not merge this branch into `feat/browser-orchestration`.
4. Remove worktree `wt/bo-o3c-dashboard-input-code`.
