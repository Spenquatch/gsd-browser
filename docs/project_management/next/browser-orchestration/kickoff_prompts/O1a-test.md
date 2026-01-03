# O1a-test Kickoff (Test)

## Scope
Add tests for O1a: response JSON shape and `final_result()` extraction path using stubs/mocks (no real browser).

## Role Boundaries
- Tests only. No production code. No docs/tasks edits in the worktree.

## Start Checklist
1. Checkout/pull orchestration branch `feat/browser-orchestration`.
2. Read `plan.md`, `tasks.json`, `session_log.md`, `O1a-spec.md`, and this prompt.
3. Set status to `in_progress`; log START; commit docs (`docs: start O1a-test`).
4. Create branch/worktree `bo-o1a-orchestrator-test` / `wt/bo-o1a-orchestrator-test`.
5. Keep docs/tasks/log edits off the worktree.

## Requirements
- Validate required JSON keys and bounded fields.
- Validate `result` maps to `final_result()` when present.
- Ensure no inline images are returned by default.

## Commands
- `uv run ruff format --check`
- `uv run pytest gsd-browser/tests -k o1a`

## End Checklist
1. Ensure commands succeed.
2. Commit worktree changes.
3. Update docs on orchestration branch (`docs: finish O1a-test`).
4. Remove worktree.

