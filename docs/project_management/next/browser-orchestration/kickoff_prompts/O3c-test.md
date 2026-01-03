# O3c-test Kickoff (Test)

## Scope
Add lightweight tests (where feasible) for client/server event wiring assumptions (primarily server-side validation remains covered by O3a/O3b). Keep this small.

## Role Boundaries
- Tests only. No production code.

## Commands
- `uv run ruff format --check`
- `uv run pytest gsd-browser/tests -k o3c`

