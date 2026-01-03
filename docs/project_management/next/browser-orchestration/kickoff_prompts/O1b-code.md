# Kickoff – O1b-code (Step callbacks + screenshot artifacts + pause gating)

## Role
Code agent: production code only. No tests. Do not edit docs/tasks/session logs from the worktree.

## Goal
Implement `O1b-spec`: record `agent_step` screenshots via browser-use step callbacks and enforce pause gating between steps, while keeping `web_eval_agent` responses compact and text-only.

## Read first
- `docs/project_management/next/browser-orchestration/plan.md`
- `docs/project_management/next/browser-orchestration/tasks.json`
- `docs/project_management/next/browser-orchestration/session_log.md`
- `docs/project_management/next/browser-orchestration/O1b-spec.md`

## Start checklist (must follow)
1. `git checkout feat/browser-orchestration && git pull --ff-only`
2. Set `O1b-code` to `in_progress` in `tasks.json` (orchestration branch only).
3. Add START entry to `session_log.md`; commit docs (`docs: start O1b-code`).
4. Create branch `bo-o1b-callbacks-code`, then worktree: `git worktree add wt/bo-o1b-callbacks-code bo-o1b-callbacks-code`.
5. Do not edit docs/tasks/session_log from the worktree.

## Constraints / guardrails
- Use browser-use step hooks (`register_new_step_callback` and/or `on_step_end`) at step boundaries.
- Record screenshots via `ScreenshotManager`; do not return images inline (response remains references only).
- Pause gating blocks progress between steps until resumed; server remains source of truth for gating.

## Required commands (record output in END entry)
- `uv run ruff format --check`
- `uv run ruff check`

## End checklist
1. Run required commands and capture outputs.
2. Commit changes inside `wt/bo-o1b-callbacks-code` (no docs edits).
3. Switch back to `feat/browser-orchestration`; mark task completed; add END entry; commit docs (`docs: finish O1b-code`). Do not merge this branch into `feat/browser-orchestration`.
4. Remove worktree `wt/bo-o1b-callbacks-code`.
