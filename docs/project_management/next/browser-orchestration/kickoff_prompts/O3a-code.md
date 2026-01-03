# O3a-code Kickoff (Code)

## Scope
Implement O3a production code only: add input socket events and enforce holder-only + paused-only gating with logging and rate limiting. No CDP dispatch yet.

## Role Boundaries
- Production code only. No tests. No docs/tasks edits in the worktree.

## Requirements
- Add server-side event handlers for input events.
- Enforce holder-only and paused-only acceptance.
- Log rejected events via security logger.

## Commands
- `uv run ruff format --check`
- `uv run ruff check`

