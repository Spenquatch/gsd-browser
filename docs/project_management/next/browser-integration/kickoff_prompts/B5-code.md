# B5-code Kickoff (Code)

## Scope
Wire CDP screencast streaming to a real Playwright Page (so `/stream` emits frames), ensure screenshot-mode emits `browser_update`, and align dashboard HUD metrics. Production code only.

## Start Checklist
1. Checkout/pull orchestration branch.
2. Read plan/tasks/session log/B5-spec/prompt.
3. Set status to `in_progress`; log START (`docs: start B5-code`).
4. Create branch/worktree `bi-b5-cdpwire-code` / `wt/bi-b5-cdpwire-code`.
5. Leave docs/tasks/log edits off the worktree.

## Requirements
- Ensure `STREAMING_MODE=cdp` results in actual `frame` events being emitted during a Playwright session.
- Ensure `STREAMING_MODE=screenshot` results in `browser_update` events being emitted during the same run path.
- Fix any `/healthz` → dashboard HUD metric key mismatch so sampler totals display correctly.
- Keep changes tightly scoped (no tests in this task).

## Commands
- `uv run ruff format --check`
- `uv run ruff check`

## End Checklist
1. Ensure commands succeed.
2. Commit production changes; update docs/session log on orchestration branch; remove worktree.

