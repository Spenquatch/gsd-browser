# Kickoff – O3a-code (Take-control server API + holder/paused gating)

## Role
Code agent: production code only. No tests. Do not edit docs/tasks/session logs from the worktree.

## Goal
Implement `O3a-spec`: add `/ctrl` input events and enforce holder-only + paused-only gating with rate limiting and security logging (no CDP dispatch yet).

## Read first
- `docs/project_management/next/browser-orchestration/plan.md`
- `docs/project_management/next/browser-orchestration/tasks.json`
- `docs/project_management/next/browser-orchestration/session_log.md`
- `docs/project_management/next/browser-orchestration/O3a-spec.md`

## Start checklist (must follow)
1. `git checkout feat/browser-orchestration && git pull --ff-only`
2. Set `O3a-code` to `in_progress` in `tasks.json` (orchestration branch only).
3. Add START entry to `session_log.md`; commit docs (`docs: start O3a-code`).
4. Create branch `bo-o3a-input-api-code`, then worktree: `git worktree add wt/bo-o3a-input-api-code bo-o3a-input-api-code`.
5. Do not edit docs/tasks/session_log from the worktree.

## Constraints / guardrails
- Enforce server-side policy: only holder SID may send inputs, and only while paused.
- Apply rate limiting and security logging for rejects; be explicit about why inputs are rejected.
- Do not attempt CDP dispatch in O3a (dispatch arrives in O3b).

## Required commands (record output in END entry)
- `uv run ruff format --check`
- `uv run ruff check`

## End checklist
1. Run required commands and capture outputs.
2. Commit changes inside `wt/bo-o3a-input-api-code` (no docs edits).
3. Switch back to `feat/browser-orchestration`; mark task completed; add END entry; commit docs (`docs: finish O3a-code`). Do not merge this branch into `feat/browser-orchestration`.
4. Remove worktree `wt/bo-o3a-input-api-code`.
