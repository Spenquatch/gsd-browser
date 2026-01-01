# B4-test Kickoff (Test)

## Scope
Create tests covering provider selection (cloud vs OSS) and config validation for browser-use upgrade. Tests/fixtures only.

## Start Checklist
1. Checkout/pull orchestration branch.
2. Read plan/tasks/session log/B4-spec/prompt.
3. Set status to `in_progress`; log START (docs: start B4-test).
4. Create branch/worktree `bi-b4-browseruse-test` / `wt/bi-b4-browseruse-test`.
5. Avoid docs/tasks/log edits in worktree.

## Requirements
- Tests mocking ChatBrowserUse and Ollama providers verifying CLI/env selection.
- Tests asserting missing API key raises helpful error when cloud provider chosen.
- Tests for OSS path ensuring fallback works without API key.

## Commands
- `uv run ruff format --check`
- `uv run pytest tests/llm/test_browseruse_providers.py`

## End Checklist
1. Ensure commands pass.
2. Commit tests; update docs/session log; remove worktree.
