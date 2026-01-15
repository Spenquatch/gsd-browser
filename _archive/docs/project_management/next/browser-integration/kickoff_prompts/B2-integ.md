# B2-integ Kickoff (Integration)

## Scope
Combine dashboard code/tests, validate CDP canvas + control channel, run telemetry script, finalize docs.

## Start Checklist
1. `git checkout feat/browser-integration && git pull --ff-only`
2. Read plan/tasks/session log/B2-spec/prompt.
3. Set `B2-integ` status to `in_progress`.
4. START entry + docs commit (`docs: start B2-integ`).
5. `git branch bi-b2-dashboard-integ feat/browser-integration`
6. `git worktree add wt/bi-b2-dashboard-integ bi-b2-dashboard-integ`
7. No docs/tasks/log edits from worktree.

## Requirements
- Merge `bi-b2-dashboard-code` + `bi-b2-dashboard-test`.
- Run telemetry script in CDP mode with API key.
- Spot-check canvas + control UI manually; update docs/runbooks after merging.

## Commands
- `uv run ruff format --check`
- `uv run ruff check`
- `uv run pytest`
- `make smoke`
- `uv run python scripts/measure_stream_latency.py --duration 10 --mode cdp`

## End Checklist
1. Ensure commands succeed; capture outputs.
2. Commit integration changes; merge into orchestration branch; update docs/session log (`docs: finish B2-integ`).
3. Remove worktree.
