# Kickoff – C2-test (Provider compatibility + prompt wrapper tests)

## Role
Test agent: tests only. No production code changes. Do not edit docs/tasks/session logs from the worktree.

## Goal
Add unit tests for `C2-spec`:
- misconfigured provider/model fails fast with actionable guidance
- prompt wrapper content includes required stop conditions and anchoring guidance

## Read first
- `docs/project_management/next/cdp-first-browser-use/plan.md`
- `docs/project_management/next/cdp-first-browser-use/tasks.json`
- `docs/project_management/next/cdp-first-browser-use/session_log.md`
- `docs/project_management/next/cdp-first-browser-use/C2-spec.md`

## Start checklist (must follow)
1. `git checkout feat/cdp-first-browser-use && git pull --ff-only`
2. Set `C2-test` to `in_progress` in `tasks.json` (orchestration branch only).
3. Add START entry to `session_log.md`; commit docs (`docs: start C2-test`).
4. Create branch `cf-c2-provider-prompt-test`, then worktree: `git worktree add wt/cf-c2-provider-prompt-test cf-c2-provider-prompt-test`.
5. Do not edit docs/tasks/session_log from the worktree.

## Required commands (record output in END entry)
- `uv run ruff format --check`
- `uv run pytest gsd-browser/tests -k c2`

## End checklist
1. Run required commands and capture outputs.
2. Commit changes inside `wt/cf-c2-provider-prompt-test` (no docs edits).
3. Switch back to `feat/cdp-first-browser-use`; mark task completed; add END entry; commit docs (`docs: finish C2-test`). Do not merge this branch into `feat/cdp-first-browser-use`.
4. Remove worktree `wt/cf-c2-provider-prompt-test`.

