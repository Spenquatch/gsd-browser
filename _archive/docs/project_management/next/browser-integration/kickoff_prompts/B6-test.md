# B6-test Kickoff (Test)

## Scope
Add unit tests for control pause/resume gating and holder semantics. Tests/fixtures only.

## Start Checklist
1. Checkout/pull orchestration branch.
2. Read plan/tasks/session log/B6-spec/prompt.
3. Set status to `in_progress`; log START (`docs: start B6-test`).
4. Create branch/worktree `bi-b6-ctrlpause-test` / `wt/bi-b6-ctrlpause-test`.
5. Avoid docs/tasks/log edits in worktree.

## Requirements
- Unit-test the control state machine transitions (holder, release, paused flag).
- Unit-test the pause gate used by `web_eval_agent` (blocks until resumed).
- No live Socket.IO server or Playwright browser required.

## Commands
- `uv run ruff format --check`
- `uv run pytest tests/streaming/test_control_pause.py`

## End Checklist
1. Ensure commands pass.
2. Commit tests; update docs/session log; remove worktree.

