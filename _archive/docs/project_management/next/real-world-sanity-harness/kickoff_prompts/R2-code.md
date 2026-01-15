# Kickoff – R2-code (Artifact harvesting + classification)

## Role
Code agent: production code only. No tests. Do not edit docs/tasks/session logs from the worktree.

## Goal
Implement `R2-spec`: retrieve screenshots + run events out-of-band and classify runs (pass/soft_fail/hard_fail).

## Read first
- `docs/project_management/next/real-world-sanity-harness/plan.md`
- `docs/project_management/next/real-world-sanity-harness/tasks.json`
- `docs/project_management/next/real-world-sanity-harness/session_log.md`
- `docs/project_management/next/real-world-sanity-harness/R2-spec.md`

## Start checklist (must follow)
1. `git checkout feat/real-world-sanity-harness && git pull --ff-only`
2. Set `R2-code` to `in_progress` in `tasks.json` (orchestration branch only).
3. Add START entry to `session_log.md`; commit docs (`docs: start R2-code`).
4. Create branch `rw-r2-artifacts-code`, then worktree: `git worktree add wt/rw-r2-artifacts-code rw-r2-artifacts-code`.
5. Do not edit docs/tasks/session_log from the worktree.

## Constraints / requirements
- Do not store request/response bodies or secrets.
- Keep artifacts bounded; prefer metadata + excerpts.
- Classification logic must be stable and deterministic.

## Required commands (record output in END entry)
- `uv run ruff format --check`
- `uv run ruff check`

## End checklist
1. Run required commands and capture outputs.
2. Commit changes inside `wt/rw-r2-artifacts-code` (no docs edits).
3. Switch back to `feat/real-world-sanity-harness`; mark task completed; add END entry; commit docs (`docs: finish R2-code`). Do not merge this branch into `feat/real-world-sanity-harness`.
4. Remove worktree `wt/rw-r2-artifacts-code`.

