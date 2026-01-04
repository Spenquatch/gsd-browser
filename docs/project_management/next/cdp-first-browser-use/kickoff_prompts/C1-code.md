# Kickoff – C1-code (Lifecycle + budgets + status mapping)

## Role
Code agent: production code only. No tests. Do not edit docs/tasks/session logs from the worktree.

## Goal
Implement `C1-spec`: remove `BrowserSession` double-start, add explicit budgets/timeouts, and define stable `status` mapping behavior for `web_eval_agent`.

## Read first
- `docs/project_management/next/cdp-first-browser-use/plan.md`
- `docs/project_management/next/cdp-first-browser-use/tasks.json`
- `docs/project_management/next/cdp-first-browser-use/session_log.md`
- `docs/project_management/next/cdp-first-browser-use/C1-spec.md`
- `docs/adr/ADR-0003-cdp-first-browser-use-integration.md`

## Start checklist (must follow)
1. `git checkout feat/cdp-first-browser-use && git pull --ff-only`
2. Set `C1-code` to `in_progress` in `tasks.json` (orchestration branch only).
3. Add START entry to `session_log.md`; commit docs (`docs: start C1-code`).
4. Create branch `cf-c1-lifecycle-code`, then worktree: `git worktree add wt/cf-c1-lifecycle-code cf-c1-lifecycle-code`.
5. Do not edit docs/tasks/session_log from the worktree.

## Constraints / requirements
- No explicit `BrowserSession.start()` in the `web_eval_agent` orchestration path unless browser-use requires it for a documented edge case.
- Ensure cleanup on exceptions/timeouts/cancellation.
- Implement defaults from the plan; allow per-call overrides (args or settings) without breaking backward compatibility.
- Ensure MCP stdio safety (no stdout logging).

## Required commands (record output in END entry)
- `uv run ruff format --check`
- `uv run ruff check`

## End checklist
1. Run required commands and capture outputs.
2. Commit changes inside `wt/cf-c1-lifecycle-code` (no docs edits).
3. Switch back to `feat/cdp-first-browser-use`; mark task completed; add END entry; commit docs (`docs: finish C1-code`). Do not merge this branch into `feat/cdp-first-browser-use`.
4. Remove worktree `wt/cf-c1-lifecycle-code`.

