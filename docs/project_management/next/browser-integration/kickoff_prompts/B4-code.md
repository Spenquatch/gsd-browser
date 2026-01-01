# B4-code Kickoff (Code)

## Scope
Upgrade `browser-use` dependency, add provider selection flags/env, wire validation. Production code only.

## Start Checklist
1. Checkout/pull orchestration branch.
2. Read plan/tasks/session log/B4-spec/prompt.
3. Set status to `in_progress`; log START (`docs: start B4-code`).
4. Create branch/worktree `bi-b4-browseruse-code` / `wt/bi-b4-browseruse-code`.
5. Leave docs/tasks/log edits off the worktree.

## Requirements
- Update pyproject/lock to latest `browser-use`.
- Add provider selection (ChatBrowserUse/OpenAI/Ollama) via CLI/env.
- Early validation errors with clear messages.

## Commands
- `uv run ruff format --check`
- `uv run ruff check`
- `poetry lock --no-update` (only if spec requires lock refresh)

## End Checklist
1. Ensure commands succeed.
2. Commit production changes; update docs/session log on orchestration branch; remove worktree.
