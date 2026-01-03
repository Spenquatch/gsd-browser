# O3c-code Kickoff (Code)

## Scope
Implement O3c production code only: update dashboard JS to capture input and emit to `/ctrl`, plus add minimal manual verification docs steps.

## Role Boundaries
- Production code only (dashboard static + docs). No tests in this task.

## Requirements
- Emit input events only when holder+paused (client-side guard), but rely on server validation.
- Add concise manual verification steps (take control, click, type incl Enter, release, resume).

## Commands
- `uv run ruff format --check`
- `uv run ruff check`

