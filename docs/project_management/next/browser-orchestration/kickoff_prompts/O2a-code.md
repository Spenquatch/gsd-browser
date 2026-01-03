# O2a-code Kickoff (Code)

## Scope
Implement O2a production code only: add an in-memory run event store keyed by `session_id` and record agent/console/network events with strict limits.

## Role Boundaries
- Production code only. No tests. No docs/tasks edits in the worktree.

## Requirements
- Store bounded, truncated events by type.
- Update `web_eval_agent` artifact counts to reflect stored events.
- Do not add new MCP tools in this triad.

## Commands
- `uv run ruff format --check`
- `uv run ruff check`

