# Kickoff – O3b-code (CDP input dispatch implementation)

## Role
Code agent: production code only. No tests. Do not edit docs/tasks/session logs from the worktree.

## Goal
Implement `O3b-spec`: route accepted input events to the active session via CDP with keyboard correctness (Enter submit sequence, modifiers, typing) and safe no-op behavior when no session is active.

## Read first
- `docs/project_management/next/browser-orchestration/plan.md`
- `docs/project_management/next/browser-orchestration/tasks.json`
- `docs/project_management/next/browser-orchestration/session_log.md`
- `docs/project_management/next/browser-orchestration/O3b-spec.md`

## Start checklist (must follow)
1. `git checkout feat/browser-orchestration && git pull --ff-only`
2. Set `O3b-code` to `in_progress` in `tasks.json` (orchestration branch only).
3. Add START entry to `session_log.md`; commit docs (`docs: start O3b-code`).
4. Create branch `bo-o3b-cdp-dispatch-code`, then worktree: `git worktree add wt/bo-o3b-cdp-dispatch-code bo-o3b-cdp-dispatch-code`.
5. Do not edit docs/tasks/session_log from the worktree.

## Constraints / guardrails
- Prefer browser-use `BrowserSession` CDP access (avoid dual CDP stacks).
- Focus on correctness of keyboard semantics (Enter submission, modifiers, printable chars) based on `~/web-agent` lessons.
- Do not dispatch inputs when no active session/page is available; log/record a clear reason.
- Dashboard wiring is O3c (do not change dashboard JS here).

## Required commands (record output in END entry)
- `uv run ruff format --check`
- `uv run ruff check`

## End checklist
1. Run required commands and capture outputs.
2. Commit changes inside `wt/bo-o3b-cdp-dispatch-code` (no docs edits).
3. Switch back to `feat/browser-orchestration`; mark task completed; add END entry; commit docs (`docs: finish O3b-code`). Do not merge this branch into `feat/browser-orchestration`.
4. Remove worktree `wt/bo-o3b-cdp-dispatch-code`.
