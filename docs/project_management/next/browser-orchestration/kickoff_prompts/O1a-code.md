# Kickoff – O1a-code (Orchestrated `web_eval_agent` + JSON response contract)

## Role
Code agent: production code only. No tests. Do not edit docs/tasks/session logs from the worktree.

## Goal
Implement `O1a-spec`: run browser-use inside `web_eval_agent`, extract `final_result()`, and return a single JSON `TextContent` response (no inline images; MCP stdio-safe).

## Read first
- `docs/project_management/next/browser-orchestration/plan.md`
- `docs/project_management/next/browser-orchestration/tasks.json`
- `docs/project_management/next/browser-orchestration/session_log.md`
- `docs/project_management/next/browser-orchestration/O1a-spec.md`

## Start checklist (must follow)
1. `git checkout feat/browser-orchestration && git pull --ff-only`
2. Set `O1a-code` to `in_progress` in `tasks.json` (orchestration branch only).
3. Add START entry to `session_log.md`; commit docs (`docs: start O1a-code`).
4. Create branch `bo-o1a-orchestrator-code`, then worktree: `git worktree add wt/bo-o1a-orchestrator-code bo-o1a-orchestrator-code`.
5. Do not edit docs/tasks/session_log from the worktree.

## Constraints / guardrails
- Use browser-use ≥0.11; extract the answer via `AgentHistoryList.final_result()`.
- Response must be JSON per `O1a-spec.md` (single `TextContent`, text-only).
- Include `session_id` and `tool_call_id`; normalize URLs.
- Ensure MCP stdio safety: no stdout output once `serve` starts (logs to stderr only).

## Required commands (record output in END entry)
- `uv run ruff format --check`
- `uv run ruff check`

## End checklist
1. Run required commands and capture outputs.
2. Commit changes inside `wt/bo-o1a-orchestrator-code` (no docs edits).
3. Switch back to `feat/browser-orchestration`; mark task completed; add END entry; commit docs (`docs: finish O1a-code`). Do not merge this branch into `feat/browser-orchestration`.
4. Remove worktree `wt/bo-o1a-orchestrator-code`.
