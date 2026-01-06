# Kickoff Prompt – A4-code (Harness actionable classification)

## Scope
- Production code only; no tests. Implement `A4-spec.md`.
- Update harness actionable predicate so agent/provider/schema failures count as actionable when artifacts exist.

## Start Checklist
1. `git checkout feat/browser-use-contract-alignment && git pull --ff-only`
2. Read: `plan.md`, `tasks.json`, `session_log.md`, `A4-spec.md`, this prompt.
3. Set `A4-code` status to `in_progress` in `tasks.json` (orchestration branch only).
4. Add START entry to `session_log.md`; commit docs (`docs: start A4-code`).
5. Create branch `buca-a4-harness-classify-code` from `feat/browser-use-contract-alignment`; run `git worktree add wt/buca-a4-harness-classify-code buca-a4-harness-classify-code`.
6. Do **not** edit docs/tasks/session_log from the worktree.

## Requirements
- Treat common agent/provider/schema failures as actionable (do not weaken `pass` semantics).
- Keep the classification rules stable and deterministic.
- Required commands:
  - `uv run ruff format --check`
  - `uv run ruff check`

## End Checklist
1. Run required commands and capture outputs.
2. Inside `wt/buca-a4-harness-classify-code`, commit changes (no docs/tasks/session_log edits).
3. Checkout `feat/browser-use-contract-alignment`; update `tasks.json` + add END entry to `session_log.md`; commit docs (`docs: finish A4-code`).
4. Remove worktree `wt/buca-a4-harness-classify-code`.

