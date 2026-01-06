# Kickoff Prompt – A2-code (Pre-teardown screenshot guarantee)

## Scope
- Production code only; no tests. Implement `A2-spec.md`.
- Move the screenshot guarantee into a pre-teardown hook/callback so early aborts still capture at least one screenshot.

## Start Checklist
1. `git checkout feat/browser-use-contract-alignment && git pull --ff-only`
2. Read: `plan.md`, `tasks.json`, `session_log.md`, `A2-spec.md`, this prompt.
3. Set `A2-code` status to `in_progress` in `tasks.json` (orchestration branch only).
4. Add START entry to `session_log.md`; commit docs (`docs: start A2-code`).
5. Create branch `buca-a2-screenshot-code` from `feat/browser-use-contract-alignment`; run `git worktree add wt/buca-a2-screenshot-code buca-a2-screenshot-code`.
6. Do **not** edit docs/tasks/session_log from the worktree.

## Requirements
- Implement pre-teardown screenshot capture using browser-use hook(s) (prefer done callback when available).
- Keep scope narrow: no harness/classification changes here.
- Required commands:
  - `uv run ruff format --check`
  - `uv run ruff check`

## End Checklist
1. Run required commands and capture outputs.
2. Inside `wt/buca-a2-screenshot-code`, commit changes (no docs/tasks/session_log edits).
3. Checkout `feat/browser-use-contract-alignment`; update `tasks.json` + add END entry to `session_log.md`; commit docs (`docs: finish A2-code`).
4. Remove worktree `wt/buca-a2-screenshot-code`.

