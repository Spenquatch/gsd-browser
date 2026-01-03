# Kickoff – O2a-code (Run event store + capture pipeline)

## Role
Code agent: production code only. No tests. Do not edit docs/tasks/session logs from the worktree.

## Goal
Implement `O2a-spec`: add an in-memory run event store keyed by `session_id` and capture bounded/truncated agent/console/network events; reflect counts in `web_eval_agent` artifacts (no new MCP tools yet).

## Read first
- `docs/project_management/next/browser-orchestration/plan.md`
- `docs/project_management/next/browser-orchestration/tasks.json`
- `docs/project_management/next/browser-orchestration/session_log.md`
- `docs/project_management/next/browser-orchestration/O2a-spec.md`

## Start checklist (must follow)
1. `git checkout feat/browser-orchestration && git pull --ff-only`
2. Set `O2a-code` to `in_progress` in `tasks.json` (orchestration branch only).
3. Add START entry to `session_log.md`; commit docs (`docs: start O2a-code`).
4. Create branch `bo-o2a-events-store-code`, then worktree: `git worktree add wt/bo-o2a-events-store-code bo-o2a-events-store-code`.
5. Do not edit docs/tasks/session_log from the worktree.

## Constraints / guardrails
- Enforce strict caps per session/type and per-field truncation (deterministic).
- Avoid storing response bodies by default; keep details bounded.
- Do not add any new MCP tools/endpoints in O2a (tool arrives in O2b).

## Required commands (record output in END entry)
- `uv run ruff format --check`
- `uv run ruff check`

## End checklist
1. Run required commands and capture outputs.
2. Commit changes inside `wt/bo-o2a-events-store-code` (no docs edits).
3. Switch back to `feat/browser-orchestration`; mark task completed; add END entry; commit docs (`docs: finish O2a-code`). Do not merge this branch into `feat/browser-orchestration`.
4. Remove worktree `wt/bo-o2a-events-store-code`.
