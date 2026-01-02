# B6-code Kickoff (Code)

## Scope
Make `/ctrl` Pause/Resume affect runtime behavior by wiring control state into `web_eval_agent`. Production code only.

## Start Checklist
1. Checkout/pull orchestration branch.
2. Read plan/tasks/session log/B6-spec/prompt.
3. Set status to `in_progress`; log START (`docs: start B6-code`).
4. Create branch/worktree `bi-b6-ctrlpause-code` / `wt/bi-b6-ctrlpause-code`.
5. Leave docs/tasks/log edits off the worktree.

## Requirements
- Expose control state from the streaming runtime in a production-safe way.
- `web_eval_agent` must block between steps when paused and resume when unpaused.
- Preserve holder-only semantics: only the control holder can pause/resume; releasing control unpauses.
- Keep changes scoped (no tests in this task).

## Commands
- `uv run ruff format --check`
- `uv run ruff check`

## End Checklist
1. Ensure commands succeed.
2. Commit production changes; update docs/session log on orchestration branch; remove worktree.

