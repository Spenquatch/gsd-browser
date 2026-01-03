# O1a-integ Kickoff (Integration)

## Scope
Merge O1a code/tests, reconcile to spec, run full suite and smoke.

## Requirements
- Merge `O1a-code` and `O1a-test`.
- Run full suite + smoke.
- Ensure `web_eval_agent` returns JSON per spec and stays text-only.

## Commands
- `uv run ruff format --check`
- `uv run ruff check`
- `uv run pytest`
- `make smoke`

