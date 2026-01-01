# B4-integ Kickoff (Integration)

## Scope
Merge browser-use upgrade code/tests, verify dependency upgrade, run full suite, finalize docs.

## Start Checklist
1. Checkout/pull orchestration branch.
2. Read plan/tasks/session log/B4-spec/prompt.
3. Set status to `in_progress`; log START (`docs: start B4-integ`).
4. Create branch/worktree `bi-b4-browseruse-integ` / `wt/bi-b4-browseruse-integ`.
5. Keep docs/tasks/log edits outside the worktree.

## Requirements
- Merge `bi-b4-browseruse-code` and `bi-b4-browseruse-test`.
- Run full suite + smoke; ensure new dependency installs cleanly.
- Update docs (README/setup) for provider selection.

## Commands
- `uv run ruff format --check`
- `uv run ruff check`
- `uv run pytest`
- `make smoke`

## End Checklist
1. Ensure commands succeed.
2. Commit integration changes; merge into orchestration branch; update docs/session log with END entry (`docs: finish B4-integ`).
3. Remove worktree.
