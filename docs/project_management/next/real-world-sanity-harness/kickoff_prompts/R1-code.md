# Kickoff – R1-code (Harness runner + scenario registry)

## Role
Code agent: production code only. No tests. Do not edit docs/tasks/session logs from the worktree.

## Goal
Implement `R1-spec`: harness CLI/script shape, scenario registry, and output bundle structure.

## Read first
- `docs/project_management/next/real-world-sanity-harness/plan.md`
- `docs/project_management/next/real-world-sanity-harness/tasks.json`
- `docs/project_management/next/real-world-sanity-harness/session_log.md`
- `docs/project_management/next/real-world-sanity-harness/R1-spec.md`
- `docs/adr/ADR-0004-real-world-sanity-harness-and-quality-gates.md`

## Start checklist (must follow)
1. `git checkout feat/real-world-sanity-harness && git pull --ff-only`
2. Set `R1-code` to `in_progress` in `tasks.json` (orchestration branch only).
3. Add START entry to `session_log.md`; commit docs (`docs: start R1-code`).
4. Create branch `rw-r1-harness-code`, then worktree: `git worktree add wt/rw-r1-harness-code rw-r1-harness-code`.
5. Do not edit docs/tasks/session_log from the worktree.

## Constraints / requirements
- Harness must remain opt-in and must not run as part of `pytest`/`make smoke`.
- Ensure output tree matches the plan.
- Avoid writing secrets to disk.

## Required commands (record output in END entry)
- `uv run ruff format --check`
- `uv run ruff check`

## End checklist
1. Run required commands and capture outputs.
2. Commit changes inside `wt/rw-r1-harness-code` (no docs edits).
3. Switch back to `feat/real-world-sanity-harness`; mark task completed; add END entry; commit docs (`docs: finish R1-code`). Do not merge this branch into `feat/real-world-sanity-harness`.
4. Remove worktree `wt/rw-r1-harness-code`.

