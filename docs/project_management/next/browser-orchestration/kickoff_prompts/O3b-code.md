# O3b-code Kickoff (Code)

## Scope
Implement O3b production code only: route input events to the active session via CDP, focusing on keyboard correctness (Enter, modifiers, typing).

## Role Boundaries
- Production code only. No tests. No docs/tasks edits in the worktree.

## Requirements
- Prefer browser-use BrowserSession CDP access.
- Implement key mapping and Enter sequence based on `~/web-agent` lessons.

## Commands
- `uv run ruff format --check`
- `uv run ruff check`

