# Browser-use Contract Alignment — Feature Plan

## Purpose
Make `web_eval_agent` reliably contract-correct with browser-use and reliably debuggable on failures:
- Remove prompt-induced `AgentOutput` validation failures (missing `action`).
- Guarantee pre-teardown artifacts (at least one step screenshot, plus an actionable error signal).
- Restore real-world sanity harness signal (`hard_fail` only when artifacts/reasons are truly missing).

This plan implements `docs/adr/ADR-0005-browser-use-contract-alignment-and-artifact-reliability.md`.

## Guardrails
- **Triads only:** every slice ships as code / test / integration. No mixed commits.
- **Code role:** production Python only (no tests). Required commands from the worktree: `uv run ruff format --check`, `uv run ruff check`.
- **Test role:** tests/fixtures/harness only. Required: `uv run ruff format --check` and targeted `uv run pytest ...`.
- **Integration role:** reconciles code+tests to the spec and must run: `uv run ruff format --check`, `uv run ruff check`, `uv run pytest`, `make smoke`.
- **Docs/tasks/session_log edits live only on the orchestration branch.** Never edit them from worktrees.
- **Privacy:** do not persist secrets; keep event capture bounded; do not store response bodies.
- **Sizing:** each task is scoped so a single agent can execute it in one session; when in doubt, split into another triad.

## Branch & Worktree Conventions
- Orchestration branch: `feat/browser-use-contract-alignment`.
- Task branches: `buca-<triad>-<scope>-<role>` (example: `buca-a1-prompt-code`).
- Worktrees: `wt/<branch>` (example: `wt/buca-a1-prompt-code`).

## References
- `docs/adr/ADR-0005-browser-use-contract-alignment-and-artifact-reliability.md`
- `docs/adr/ADR-0003-cdp-first-browser-use-integration.md` (contract background + failure modes)
- `gsd-browser/src/gsd_browser/mcp_server.py` (prompt wrapper + orchestration)
- `gsd-browser/src/gsd_browser/run_event_store.py` (event storage contract)
- `gsd-browser/src/gsd_browser/real_world_sanity.py` (harness actionable predicate + classification)

## Triad Overview
1. **A1 – Prompt wrapper contract alignment**
   - Express stop conditions and completion via browser-use’s `done` action (no alternate schema).
2. **A2 – Pre-teardown screenshot guarantee**
   - Guarantee at least one screenshot is captured before browser-use session teardown (especially on early aborts).
3. **A3 – Persist LLM/provider/schema failures as run events**
   - Record “AgentOutput validation / provider error” as `RunEventStore` error events so failures are debuggable.
4. **A4 – Harness actionable classification for agent failures**
   - Treat the common “agent/provider/schema” failures as actionable so expected failures become `soft_fail`, not `hard_fail`.

## Start Checklist (all tasks)
1. `git checkout feat/browser-use-contract-alignment && git pull --ff-only`
2. Read this plan, `tasks.json`, `session_log.md`, the triad spec, and your kickoff prompt.
3. Set the task status to `in_progress` in `tasks.json` (on the orchestration branch).
4. Add a START entry to `session_log.md`; commit docs (`docs: start <task-id>`).
5. Create the task branch from `feat/browser-use-contract-alignment`; add the worktree: `git worktree add wt/<branch> <branch>`.
6. Do **not** edit docs/tasks/session log within the worktree.

## End Checklist (code/test)
1. Run required commands (code: `uv run ruff format --check`, `uv run ruff check`; test: same + targeted `uv run pytest ...`). Capture outputs.
2. Inside the worktree, commit task changes (no docs updates).
3. Checkout `feat/browser-use-contract-alignment`; update `tasks.json` status and add END entry to `session_log.md`; commit docs (`docs: finish <task-id>`).
4. Remove the worktree: `git worktree remove wt/<branch>`.

## End Checklist (integration)
1. Merge code/test branches into the integration worktree; reconcile behavior with the spec.
2. Run `uv run ruff format --check`, `uv run ruff check`, `uv run pytest`, `make smoke`. Capture outputs.
3. Commit integration changes on the integration branch.
4. Fast-forward merge the integration branch into `feat/browser-use-contract-alignment`; update `tasks.json` and `session_log.md` with the END entry; commit docs (`docs: finish <task-id>`).
5. Remove the worktree.
