# O2a-test Kickoff (Test)

## Scope
Add tests for O2a: event store limits, truncation, and basic per-session/type filtering primitives.

## Role Boundaries
- Tests only. No production code. No docs/tasks edits in the worktree.

## Commands
- `uv run ruff format --check`
- `uv run pytest gsd-browser/tests -k o2a`

