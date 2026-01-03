# Kickoff – O2b-code (`get_run_events` tool + response modes)

## Role
Code agent: production code only. No tests. Do not edit docs/tasks/session logs from the worktree.

## Goal
Implement `O2b-spec`: add `get_run_events` (JSON text) and add `web_eval_agent` response modes (`compact` vs `dev`) with sane defaults and strict bounds.

## Read first
- `docs/project_management/next/browser-orchestration/plan.md`
- `docs/project_management/next/browser-orchestration/tasks.json`
- `docs/project_management/next/browser-orchestration/session_log.md`
- `docs/project_management/next/browser-orchestration/O2b-spec.md`

## Start checklist (must follow)
1. `git checkout feat/browser-orchestration && git pull --ff-only`
2. Set `O2b-code` to `in_progress` in `tasks.json` (orchestration branch only).
3. Add START entry to `session_log.md`; commit docs (`docs: start O2b-code`).
4. Create branch `bo-o2b-run-events-tool-code`, then worktree: `git worktree add wt/bo-o2b-run-events-tool-code bo-o2b-run-events-tool-code`.
5. Do not edit docs/tasks/session_log from the worktree.

## Constraints / guardrails
- `get_run_events` must enforce filters + strict max limits; return JSON per `O2b-spec.md`.
- `web_eval_agent` gains `mode` selection with sensible defaults (localhost/127.0.0.1 => `dev`, otherwise `compact`), with explicit argument override.
- In `dev` mode, include bounded console/network excerpts; `compact` stays small and reference-driven.

## Required commands (record output in END entry)
- `uv run ruff format --check`
- `uv run ruff check`

## End checklist
1. Run required commands and capture outputs.
2. Commit changes inside `wt/bo-o2b-run-events-tool-code` (no docs edits).
3. Switch back to `feat/browser-orchestration`; mark task completed; add END entry; commit docs (`docs: finish O2b-code`). Do not merge this branch into `feat/browser-orchestration`.
4. Remove worktree `wt/bo-o2b-run-events-tool-code`.
