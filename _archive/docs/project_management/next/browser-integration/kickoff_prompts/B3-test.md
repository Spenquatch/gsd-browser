# B3-test Kickoff (Test)

## Scope
Author pytest coverage for screenshot filters and MCP tool envelopes. Tests only.

## Start Checklist
1. Checkout/pull orchestration branch.
2. Read plan/tasks/session log/B3-spec/prompt.
3. Set task status to `in_progress` and log START.
4. Create branch `bi-b3-mcp-test` and worktree `wt/bi-b3-mcp-test`.
5. Avoid docs/tasks/log edits inside worktree.

## Requirements
- Tests hitting `ScreenshotManager.get_screenshots` filtering combos.
- Tests verifying MCP `get_screenshots` enforces `last_n ≤ 20` and metadata-only mode.
- Tests for CLI diagnostics (mock log server, ensure messages).

## Commands
- `uv run ruff format --check`
- `uv run pytest tests/mcp/test_screenshot_tool.py`

## End Checklist
1. Ensure commands pass.
2. Commit tests; update docs/session log on orchestration branch; remove worktree.
