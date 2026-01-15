# Kickoff Prompt – A1-code (Prompt wrapper contract alignment)

## Scope
- Production code only; no tests. Implement `A1-spec.md`.
- Align the prompt wrapper with browser-use’s `AgentOutput` contract by removing any instruction that would cause the model to omit `action`.

## Start Checklist
1. `git checkout feat/browser-use-contract-alignment && git pull --ff-only`
2. Read: `plan.md`, `tasks.json`, `session_log.md`, `A1-spec.md`, this prompt.
3. Set `A1-code` status to `in_progress` in `tasks.json` (orchestration branch only).
4. Add START entry to `session_log.md`; commit docs (`docs: start A1-code`).
5. Create branch `buca-a1-prompt-code` from `feat/browser-use-contract-alignment`; run `git worktree add wt/buca-a1-prompt-code buca-a1-prompt-code`.
6. Do **not** edit docs/tasks/session_log from the worktree.

## Requirements
- Update the wrapper to:
  - anchor to the base URL
  - define stop conditions
  - instruct completion/stopping only via a single `done(success=..., text=...)` action
- Do not instruct a custom “JSON object only” response shape during the action loop.
- Required commands:
  - `uv run ruff format --check`
  - `uv run ruff check`

## End Checklist
1. Run required commands and capture outputs.
2. Inside `wt/buca-a1-prompt-code`, commit changes (no docs/tasks/session_log edits).
3. Checkout `feat/browser-use-contract-alignment`; update `tasks.json` + add END entry to `session_log.md`; commit docs (`docs: finish A1-code`).
4. Remove worktree `wt/buca-a1-prompt-code`.

