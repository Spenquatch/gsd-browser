# B5-test Kickoff (Test)

## Scope
Add unit tests for CDP wiring behavior and sampler totals without requiring a real Playwright browser. Tests/fixtures only.

## Start Checklist
1. Checkout/pull orchestration branch.
2. Read plan/tasks/session log/B5-spec/prompt.
3. Set status to `in_progress`; log START (`docs: start B5-test`).
4. Create branch/worktree `bi-b5-cdpwire-test` / `wt/bi-b5-cdpwire-test`.
5. Avoid docs/tasks/log edits in worktree.

## Requirements
- Tests simulate CDP frame callback → stats update + sampled screenshot storage.
- Tests validate screenshot-mode emission path (e.g., `emit_browser_update`) and resulting stored screenshots/stats.
- Tests should not be flaky and should not require network, real browser, or a live Socket.IO server.

## Commands
- `uv run ruff format --check`
- `uv run pytest tests/streaming/test_cdp_wiring.py`

## End Checklist
1. Ensure commands pass.
2. Commit tests; update docs/session log; remove worktree.

