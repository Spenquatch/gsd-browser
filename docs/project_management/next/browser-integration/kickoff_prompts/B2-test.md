# B2-test Kickoff (Test)

## Scope
Write tests for dashboard security: API key auth, nonce signing/validation, rate limiting, telemetry script harness. Tests only.

## Start Checklist
1. `git checkout feat/browser-integration && git pull --ff-only`
2. Read plan/tasks/session log/B2-spec/this prompt.
3. Set `B2-test` status to `in_progress`.
4. Add START entry; commit docs (`docs: start B2-test`).
5. `git branch bi-b2-dashboard-test feat/browser-integration`
6. `git worktree add wt/bi-b2-dashboard-test bi-b2-dashboard-test`
7. No docs/tasks/log edits from worktree.

## Requirements
- Tests for `ensure_authenticated`, `_issue_nonce_for_sid`, `_verify_nonce_for_sid`, and rate limiter behavior.
- Tests validating allowed origins and Socket.IO auth rejection.
- Unit test for telemetry script (mock sockets) verifying latency JSON parsing.

## Commands
- `uv run ruff format --check`
- `uv run pytest tests/dashboard/test_security.py`

## End Checklist
1. Ensure commands pass.
2. Commit test files.
3. Update tasks/session log; commit docs (`docs: finish B2-test`).
4. Remove worktree.
