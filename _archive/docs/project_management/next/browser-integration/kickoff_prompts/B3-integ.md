# B3-integ Kickoff (Integration)

## Scope
Merge MCP tool code/tests, ensure scripts run, update docs per spec.

## Start Checklist
1. Checkout/pull orchestration branch.
2. Read plan/tasks/session log/B3-spec/prompt.
3. Set status to `in_progress`; log START (docs: start B3-integ).
4. Create branch/worktree `bi-b3-mcp-integ` / `wt/bi-b3-mcp-integ`.
5. Keep docs/tasks/log edits off the worktree.

## Requirements
- Merge code/test branches, resolve drift.
- Run CLI diagnostics + `make smoke` verifying MCP tools.
- Update README/docs after merging.

## Commands
- `uv run ruff format --check`
- `uv run ruff check`
- `uv run pytest`
- `make smoke`

## End Checklist
1. Ensure commands succeed.
2. Commit integration work; merge into orchestration branch; update docs/session log (docs: finish B3-integ).
3. Remove worktree.
