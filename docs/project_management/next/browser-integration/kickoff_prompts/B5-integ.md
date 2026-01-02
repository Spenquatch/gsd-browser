# B5-integ Kickoff (Integration)

## Scope
Merge CDP wiring code/tests, verify end-to-end `frame`/`browser_update` emission in the dashboard, run full suite, and update docs as needed.

## Start Checklist
1. Checkout/pull orchestration branch.
2. Read plan/tasks/session log/B5-spec/prompt.
3. Set status to `in_progress`; log START (`docs: start B5-integ`).
4. Create branch/worktree `bi-b5-cdpwire-integ` / `wt/bi-b5-cdpwire-integ`.
5. Keep docs/tasks/log edits off the worktree.

## Requirements
- Merge `bi-b5-cdpwire-code` and `bi-b5-cdpwire-test`.
- Run full suite + smoke.
- Manually validate (briefly) that CDP mode yields non-zero frames for telemetry and that sampler totals display on the dashboard.

## Commands
- `uv run ruff format --check`
- `uv run ruff check`
- `uv run pytest`
- `make smoke`
- `uv run python scripts/measure_stream_latency.py --duration 10 --mode cdp`

## End Checklist
1. Ensure commands succeed.
2. Commit integration changes; merge into orchestration branch; update docs/session log with END entry (`docs: finish B5-integ`).
3. Remove worktree.

