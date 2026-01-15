# B1-integ Kickoff (Integration)

## Scope
Merge B1 code/test branches, ensure CDP vs screenshot streaming works, update docs per spec, and run full suite.

## Start Checklist
1. `git checkout feat/browser-integration && git pull --ff-only`
2. Read `plan.md`, `tasks.json`, `session_log.md`, `B1-spec.md`, and this prompt.
3. Set `B1-integ` status to `in_progress` in `tasks.json`.
4. Add START entry to `session_log.md`; commit docs (`docs: start B1-integ`).
5. `git branch bi-b1-streaming-integ feat/browser-integration`
6. `git worktree add wt/bi-b1-streaming-integ bi-b1-streaming-integ`
7. No docs/tasks/session log edits in the worktree.

## Requirements
- Merge `bi-b1-streaming-code` and `bi-b1-streaming-test` into the integration branch.
- Verify CDP mode and screenshot fallback manually (brief smoke) and ensure `/healthz` responds correctly.
- Update docs/README as needed (done on orchestration branch after merging).

## Commands (run inside worktree before committing)
- `uv run ruff format --check`
- `uv run ruff check`
- `uv run pytest`
- `make smoke`

## End Checklist
1. Ensure commands + manual checks complete, capture outputs.
2. Commit integration changes in `wt/bi-b1-streaming-integ`.
3. Merge integration branch fast-forward into `feat/browser-integration`; update `tasks.json`/`session_log.md` with END entry; commit docs (`docs: finish B1-integ`).
4. `git worktree remove wt/bi-b1-streaming-integ`.
