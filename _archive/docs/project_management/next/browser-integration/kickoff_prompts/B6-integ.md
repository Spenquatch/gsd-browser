# B6-integ Kickoff (Integration)

## Scope
Merge pause wiring code/tests, run full suite, and add minimal manual verification steps to docs.

## Start Checklist
1. Checkout/pull orchestration branch.
2. Read plan/tasks/session log/B6-spec/prompt.
3. Set status to `in_progress`; log START (`docs: start B6-integ`).
4. Create branch/worktree `bi-b6-ctrlpause-integ` / `wt/bi-b6-ctrlpause-integ`.
5. Keep docs/tasks/log edits off the worktree.

## Requirements
- Merge `bi-b6-ctrlpause-code` and `bi-b6-ctrlpause-test`.
- Run full suite + smoke.
- Update docs with “how to verify pause/resume” (after merging to orchestration branch).

## Commands
- `uv run ruff format --check`
- `uv run ruff check`
- `uv run pytest`
- `make smoke`

## End Checklist
1. Ensure commands succeed.
2. Commit integration changes; merge into orchestration branch; update docs/session log with END entry (`docs: finish B6-integ`).
3. Remove worktree.

