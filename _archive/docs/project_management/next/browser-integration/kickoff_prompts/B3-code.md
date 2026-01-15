# B3-code Kickoff (Code)

## Scope
Implement MCP tools (`web_eval_agent`, `setup_browser_state`, `get_screenshots`), screenshot filtering logic, and diagnostic scripts. No tests.

## Start Checklist
1. `git checkout feat/browser-integration && git pull --ff-only`
2. Read plan/tasks/session log/B3-spec/prompt.
3. Set `B3-code` status to `in_progress`.
4. START entry + docs commit (`docs: start B3-code`).
5. `git branch bi-b3-mcp-code feat/browser-integration`
6. `git worktree add wt/bi-b3-mcp-code bi-b3-mcp-code`
7. Avoid docs/tasks/log edits from worktree.

## Requirements
- Register MCP tools via FastMCP with docstrings + parameters identical to web-agent.
- Implement screenshot filtering + metadata responses.
- Port diagnostics scripts (diagnose/smoke/mcp_tool_smoke) to template CLI.

## Commands
- `uv run ruff format --check`
- `uv run ruff check`

## End Checklist
1. Ensure commands pass; capture outputs.
2. Commit production changes.
3. Update docs/session log (on orchestration branch) and remove worktree.
