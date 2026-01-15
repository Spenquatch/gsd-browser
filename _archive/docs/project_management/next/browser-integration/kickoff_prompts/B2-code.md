# B2-code Kickoff (Code)

## Scope
Port dashboard UI static assets, Socket.IO control namespace, HUD updates, and auth enforcement (API key, nonce, rate limiting) per `B2-spec.md`. Production assets and server code only.

## Start Checklist
1. `git checkout feat/browser-integration && git pull --ff-only`
2. Read plan/tasks/session log/B2-spec/prompt.
3. Set `B2-code` status to `in_progress` in `tasks.json`.
4. Add START entry to `session_log.md`; commit docs (`docs: start B2-code`).
5. `git branch bi-b2-dashboard-code feat/browser-integration`
5. `git worktree add wt/bi-b2-dashboard-code bi-b2-dashboard-code`
6. Keep docs/tasks/log edits off the worktree.

## Requirements
- Copy dashboard HTML/CSS/JS, integrate canvas renderer, HUD, buttons.
- Implement Socket.IO `/stream` + `/ctrl` namespaces with API key + nonce enforcement.
- Rate limiter per SID and security logging.
- Update telemetry endpoints and placeholder docs (without editing plan/tasks from worktree).

## Commands
- `uv run ruff format --check`
- `uv run ruff check`
- `npm run build` (if frontend assets require bundling)

## End Checklist
1. Ensure commands succeed.
2. Commit production code/assets inside worktree.
3. Update tasks/session log on orchestration branch; commit docs (`docs: finish B2-code`).
4. Remove worktree.
