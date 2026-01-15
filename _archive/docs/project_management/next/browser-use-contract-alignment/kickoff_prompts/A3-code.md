# Kickoff Prompt – A3-code (Persist agent/provider failures as run events)

## Scope
- Production code only; no tests. Implement `A3-spec.md`.
- Persist LLM/provider/schema validation failures into `RunEventStore` as `has_error=true` agent events.

## Start Checklist
1. `git checkout feat/browser-use-contract-alignment && git pull --ff-only`
2. Read: `plan.md`, `tasks.json`, `session_log.md`, `A3-spec.md`, this prompt.
3. Set `A3-code` status to `in_progress` in `tasks.json` (orchestration branch only).
4. Add START entry to `session_log.md`; commit docs (`docs: start A3-code`).
5. Create branch `buca-a3-run-events-code` from `feat/browser-use-contract-alignment`; run `git worktree add wt/buca-a3-run-events-code buca-a3-run-events-code`.
6. Do **not** edit docs/tasks/session_log from the worktree.

## Requirements
- Record early abort failures as run events (privacy-safe + bounded):
  - schema validation failures (`AgentOutput` parse/validation)
  - provider failures (ModelProviderError / equivalent)
- Required commands:
  - `uv run ruff format --check`
  - `uv run ruff check`

## End Checklist
1. Run required commands and capture outputs.
2. Inside `wt/buca-a3-run-events-code`, commit changes (no docs/tasks/session_log edits).
3. Checkout `feat/browser-use-contract-alignment`; update `tasks.json` + add END entry to `session_log.md`; commit docs (`docs: finish A3-code`).
4. Remove worktree `wt/buca-a3-run-events-code`.

