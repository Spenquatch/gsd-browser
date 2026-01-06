# Kickoff Prompt – A1-test (Prompt wrapper contract alignment)

## Scope
- Tests only; no production code. Implement `A1-spec.md` acceptance tests.

## Start Checklist
1. `git checkout feat/browser-use-contract-alignment && git pull --ff-only`
2. Read: `plan.md`, `tasks.json`, `session_log.md`, `A1-spec.md`, this prompt.
3. Set `A1-test` status to `in_progress` in `tasks.json` (orchestration branch only).
4. Add START entry to `session_log.md`; commit docs (`docs: start A1-test`).
5. Create branch `buca-a1-prompt-test` from `feat/browser-use-contract-alignment`; run `git worktree add wt/buca-a1-prompt-test buca-a1-prompt-test`.
6. Do **not** edit docs/tasks/session_log from the worktree.

## Requirements
- Add/update a deterministic unit test that asserts:
  - wrapper does not instruct alternate output schema (e.g., “single-line JSON object only”)
  - wrapper does instruct `done(success=...)` semantics
- Required commands:
  - `uv run ruff format --check`
  - `uv run pytest gsd-browser/tests -k \"prompt_wrapper\"`

## End Checklist
1. Run required commands and capture outputs.
2. Inside `wt/buca-a1-prompt-test`, commit changes (no docs/tasks/session_log edits).
3. Checkout `feat/browser-use-contract-alignment`; update `tasks.json` + add END entry to `session_log.md`; commit docs (`docs: finish A1-test`).
4. Remove worktree `wt/buca-a1-prompt-test`.

