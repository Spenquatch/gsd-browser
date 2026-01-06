# Kickoff Prompt – A2-test (Pre-teardown screenshot guarantee)

## Scope
- Tests only; no production code. Implement `A2-spec.md` acceptance tests.

## Start Checklist
1. `git checkout feat/browser-use-contract-alignment && git pull --ff-only`
2. Read: `plan.md`, `tasks.json`, `session_log.md`, `A2-spec.md`, this prompt.
3. Set `A2-test` status to `in_progress` in `tasks.json` (orchestration branch only).
4. Add START entry to `session_log.md`; commit docs (`docs: start A2-test`).
5. Create branch `buca-a2-screenshot-test` from `feat/browser-use-contract-alignment`; run `git worktree add wt/buca-a2-screenshot-test buca-a2-screenshot-test`.
6. Do **not** edit docs/tasks/session_log from the worktree.

## Requirements
- Add deterministic tests simulating early abort and asserting at least one `agent_step` screenshot is recorded.
- Required commands:
  - `uv run ruff format --check`
  - `uv run pytest gsd-browser/tests -k \"screenshot\"`

## End Checklist
1. Run required commands and capture outputs.
2. Inside `wt/buca-a2-screenshot-test`, commit changes (no docs/tasks/session_log edits).
3. Checkout `feat/browser-use-contract-alignment`; update `tasks.json` + add END entry to `session_log.md`; commit docs (`docs: finish A2-test`).
4. Remove worktree `wt/buca-a2-screenshot-test`.

