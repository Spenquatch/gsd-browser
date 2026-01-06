# Kickoff Prompt – A3-test (Persist agent/provider failures as run events)

## Scope
- Tests only; no production code. Implement `A3-spec.md` acceptance tests.

## Start Checklist
1. `git checkout feat/browser-use-contract-alignment && git pull --ff-only`
2. Read: `plan.md`, `tasks.json`, `session_log.md`, `A3-spec.md`, this prompt.
3. Set `A3-test` status to `in_progress` in `tasks.json` (orchestration branch only).
4. Add START entry to `session_log.md`; commit docs (`docs: start A3-test`).
5. Create branch `buca-a3-run-events-test` from `feat/browser-use-contract-alignment`; run `git worktree add wt/buca-a3-run-events-test buca-a3-run-events-test`.
6. Do **not** edit docs/tasks/session_log from the worktree.

## Requirements
- Add deterministic tests asserting provider/schema failures emit `has_error=true` agent run events.
- Required commands:
  - `uv run ruff format --check`
  - `uv run pytest gsd-browser/tests -k \"run_event\"`

## End Checklist
1. Run required commands and capture outputs.
2. Inside `wt/buca-a3-run-events-test`, commit changes (no docs/tasks/session_log edits).
3. Checkout `feat/browser-use-contract-alignment`; update `tasks.json` + add END entry to `session_log.md`; commit docs (`docs: finish A3-test`).
4. Remove worktree `wt/buca-a3-run-events-test`.

