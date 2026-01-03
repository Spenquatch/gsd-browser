# O1a-code Kickoff (Code)

## Scope
Implement O1a production code only: orchestrated `web_eval_agent` that runs browser-use and returns a single JSON `TextContent` response with explicit `final_result()` extraction. No screenshots and no pause gating in this triad.

## Role Boundaries
- Production code only. No tests. No docs/tasks edits in the worktree.

## Start Checklist
1. Checkout/pull orchestration branch `feat/browser-orchestration`.
2. Read `plan.md`, `tasks.json`, `session_log.md`, `O1a-spec.md`, and this prompt.
3. Set status to `in_progress`; log START; commit docs (`docs: start O1a-code`).
4. Create branch/worktree `bo-o1a-orchestrator-code` / `wt/bo-o1a-orchestrator-code`.
5. Keep docs/tasks/log edits off the worktree.

## Requirements
- Use browser-use ≥0.11: `Agent.run()` returns `AgentHistoryList`; extract via `final_result()`.
- Response must be JSON per `O1a-spec.md` (single `TextContent`, no images).
- Normalize URLs and include `session_id` + `tool_call_id`.
- Ensure MCP stdio safety: no stdout output once `serve` starts (stderr-only logging).

## Commands
- `uv run ruff format --check`
- `uv run ruff check`

## End Checklist
1. Ensure commands succeed.
2. Commit worktree changes.
3. Update docs on orchestration branch (`docs: finish O1a-code`).
4. Remove worktree.

