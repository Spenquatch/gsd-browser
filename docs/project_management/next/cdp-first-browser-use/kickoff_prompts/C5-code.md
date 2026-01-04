# Kickoff – C5-code (Run events + ranked failure reporting)

## Role
Code agent: production code only. No tests. Do not edit docs/tasks/session logs from the worktree.

## Goal
Implement `C5-spec`: improve run event capture robustness, add error ranking, and include bounded failure context in `web_eval_agent` JSON responses.

## Read first
- `docs/project_management/next/cdp-first-browser-use/plan.md`
- `docs/project_management/next/cdp-first-browser-use/tasks.json`
- `docs/project_management/next/cdp-first-browser-use/session_log.md`
- `docs/project_management/next/cdp-first-browser-use/C5-spec.md`
- `docs/adr/ADR-0003-cdp-first-browser-use-integration.md`

## Start checklist (must follow)
1. `git checkout feat/cdp-first-browser-use && git pull --ff-only`
2. Set `C5-code` to `in_progress` in `tasks.json` (orchestration branch only).
3. Add START entry to `session_log.md`; commit docs (`docs: start C5-code`).
4. Create branch `cf-c5-events-reporting-code`, then worktree: `git worktree add wt/cf-c5-events-reporting-code cf-c5-events-reporting-code`.
5. Do not edit docs/tasks/session_log from the worktree.

## Constraints / requirements
- Do not capture response bodies or secrets.
- Error ranking must de-emphasize common noise (telemetry/WAF) and highlight likely-causal failures.
- Compact `web_eval_agent` response stays bounded; artifacts remain out-of-band.

## Required commands (record output in END entry)
- `uv run ruff format --check`
- `uv run ruff check`

## End checklist
1. Run required commands and capture outputs.
2. Commit changes inside `wt/cf-c5-events-reporting-code` (no docs edits).
3. Switch back to `feat/cdp-first-browser-use`; mark task completed; add END entry; commit docs (`docs: finish C5-code`). Do not merge this branch into `feat/cdp-first-browser-use`.
4. Remove worktree `wt/cf-c5-events-reporting-code`.

