# O2b-code Kickoff (Code)

## Scope
Implement O2b production code only: add `get_run_events` MCP tool and add `compact` vs `dev` response mode selection for `web_eval_agent`.

## Role Boundaries
- Production code only. No tests. No docs/tasks edits in the worktree.

## Requirements
- `get_run_events` returns JSON per spec with strict limits and filters.
- `web_eval_agent` gains a `mode` argument with sensible defaults (localhost => dev; else compact).
- In dev mode, include bounded console/network excerpts; compact stays small.

## Commands
- `uv run ruff format --check`
- `uv run ruff check`

