# Kickoff – C2-code (Provider compatibility + prompt wrapper)

## Role
Code agent: production code only. No tests. Do not edit docs/tasks/session logs from the worktree.

## Goal
Implement `C2-spec`: make provider/model behavior explicit for browser-use structured output and add a browser-use-native prompt wrapper with stop conditions.

## Read first
- `docs/project_management/next/cdp-first-browser-use/plan.md`
- `docs/project_management/next/cdp-first-browser-use/tasks.json`
- `docs/project_management/next/cdp-first-browser-use/session_log.md`
- `docs/project_management/next/cdp-first-browser-use/C2-spec.md`
- `docs/adr/ADR-0003-cdp-first-browser-use-integration.md`

## Start checklist (must follow)
1. `git checkout feat/cdp-first-browser-use && git pull --ff-only`
2. Set `C2-code` to `in_progress` in `tasks.json` (orchestration branch only).
3. Add START entry to `session_log.md`; commit docs (`docs: start C2-code`).
4. Create branch `cf-c2-provider-prompt-code`, then worktree: `git worktree add wt/cf-c2-provider-prompt-code cf-c2-provider-prompt-code`.
5. Do not edit docs/tasks/session_log from the worktree.

## Constraints / requirements
- Prefer explicit, actionable failure messages over silent fallbacks.
- Prompt wrapper must be applied using browser-use configuration surfaces (extend/override system message), not a bespoke LLM prompt builder.

## Required commands (record output in END entry)
- `uv run ruff format --check`
- `uv run ruff check`

## End checklist
1. Run required commands and capture outputs.
2. Commit changes inside `wt/cf-c2-provider-prompt-code` (no docs edits).
3. Switch back to `feat/cdp-first-browser-use`; mark task completed; add END entry; commit docs (`docs: finish C2-code`). Do not merge this branch into `feat/cdp-first-browser-use`.
4. Remove worktree `wt/cf-c2-provider-prompt-code`.

