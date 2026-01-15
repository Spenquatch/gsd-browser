# Kickoff – C4-code (CDP-first streaming adapter)

## Role
Code agent: production code only. No tests. Do not edit docs/tasks/session logs from the worktree.

## Goal
Implement `C4-spec`: drive streaming via browser-use CDP sessions and sample frames into `ScreenshotManager`.

## Read first
- `docs/project_management/next/cdp-first-browser-use/plan.md`
- `docs/project_management/next/cdp-first-browser-use/tasks.json`
- `docs/project_management/next/cdp-first-browser-use/session_log.md`
- `docs/project_management/next/cdp-first-browser-use/C4-spec.md`
- `docs/adr/ADR-0003-cdp-first-browser-use-integration.md`

## Start checklist (must follow)
1. `git checkout feat/cdp-first-browser-use && git pull --ff-only`
2. Set `C4-code` to `in_progress` in `tasks.json` (orchestration branch only).
3. Add START entry to `session_log.md`; commit docs (`docs: start C4-code`).
4. Create branch `cf-c4-streaming-code`, then worktree: `git worktree add wt/cf-c4-streaming-code cf-c4-streaming-code`.
5. Do not edit docs/tasks/session_log from the worktree.

## Constraints / requirements
- Do not assume Playwright `Page` identity matches the agent’s active page.
- Attach to browser-use focused `CDPSession` via `BrowserSession.get_or_create_cdp_session()` and scope commands/events with `CDPSession.session_id`.
- Subscribe to CDP events via `cdp_client.register.*` (handler signature includes `cdp_session_id`).
- Ensure streaming stops on run end and doesn’t leak between sessions.
- If CDP attach fails, disable streaming for the run; do not fall back to Playwright CDP sessions.

## Required commands (record output in END entry)
- `uv run ruff format --check`
- `uv run ruff check`

## End checklist
1. Run required commands and capture outputs.
2. Commit changes inside `wt/cf-c4-streaming-code` (no docs edits).
3. Switch back to `feat/cdp-first-browser-use`; mark task completed; add END entry; commit docs (`docs: finish C4-code`). Do not merge this branch into `feat/cdp-first-browser-use`.
4. Remove worktree `wt/cf-c4-streaming-code`.
