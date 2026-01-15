# Kickoff Prompt – A3-integ (Persist agent/provider failures as run events)

## Scope
- Integration only. Merge A3 code+tests, reconcile to `A3-spec.md`, and ensure green checks.

## Start Checklist
1. `git checkout feat/browser-use-contract-alignment && git pull --ff-only`
2. Read: `plan.md`, `tasks.json`, `session_log.md`, `A3-spec.md`, this prompt.
3. Set `A3-integ` status to `in_progress` in `tasks.json` (orchestration branch only).
4. Add START entry to `session_log.md`; commit docs (`docs: start A3-integ`).
5. Create branch `buca-a3-run-events-integ` from `feat/browser-use-contract-alignment`; run `git worktree add wt/buca-a3-run-events-integ buca-a3-run-events-integ`.
6. Do **not** edit docs/tasks/session_log from the worktree.

## Requirements
- Merge `buca-a3-run-events-code` + `buca-a3-run-events-test` and reconcile any drift to spec.
- Required commands:
  - `uv run ruff format --check`
  - `uv run ruff check`
  - `uv run pytest`
  - `make smoke`

## End Checklist
1. Run required commands and capture outputs.
2. Inside `wt/buca-a3-run-events-integ`, commit integration changes (no docs/tasks/session_log edits).
3. Checkout `feat/browser-use-contract-alignment`; update `tasks.json` + add END entry to `session_log.md`; commit docs (`docs: finish A3-integ`).
4. Remove worktree `wt/buca-a3-run-events-integ`.

