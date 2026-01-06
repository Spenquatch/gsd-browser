# Kickoff Prompt – A4-test (Harness actionable classification)

## Scope
- Tests only; no production code. Implement `A4-spec.md` acceptance tests.

## Start Checklist
1. `git checkout feat/browser-use-contract-alignment && git pull --ff-only`
2. Read: `plan.md`, `tasks.json`, `session_log.md`, `A4-spec.md`, this prompt.
3. Set `A4-test` status to `in_progress` in `tasks.json` (orchestration branch only).
4. Add START entry to `session_log.md`; commit docs (`docs: start A4-test`).
5. Create branch `buca-a4-harness-classify-test` from `feat/browser-use-contract-alignment`; run `git worktree add wt/buca-a4-harness-classify-test buca-a4-harness-classify-test`.
6. Do **not** edit docs/tasks/session_log from the worktree.

## Requirements
- Add fixture-based tests covering classification outcomes for agent/provider/schema failures.
- Required commands:
  - `uv run ruff format --check`
  - `uv run pytest gsd-browser/tests -k \"real_world_sanity\"`

## End Checklist
1. Run required commands and capture outputs.
2. Inside `wt/buca-a4-harness-classify-test`, commit changes (no docs/tasks/session_log edits).
3. Checkout `feat/browser-use-contract-alignment`; update `tasks.json` + add END entry to `session_log.md`; commit docs (`docs: finish A4-test`).
4. Remove worktree `wt/buca-a4-harness-classify-test`.

