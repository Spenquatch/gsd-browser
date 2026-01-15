# Browser Orchestration Feature Plan

## Purpose
Make `gsd-browser` behave like a real MCP “web eval agent”: the LLM client dispatches `web_eval_agent(url, task, …)` and receives back a structured text report that includes an explicit result, plus artifact references (screenshots, streaming samples, run events) without bloating the context.

This work folds together:
- Upstream orchestration concepts from `Operative-Sh/web-eval-agent` (FastMCP tool → handler → browser-use Agent loop → formatted report).
- Proven enhancements from our local `~/web-agent` (CDP streaming, true take-control with input routing, robust screenshot storage, and “final answer” extraction).
- Newer `browser-use` APIs (≥0.11): `AgentHistoryList.final_result()`, structured output helpers, lifecycle callbacks, and BrowserSession CDP access.

## Guardrails
- **Triads only:** every slice ships as code / test / integration. No mixed commits.
- **Code role:** production Python/TS/static assets only (no tests). Required commands from the worktree: `uv run ruff format --check`, `uv run ruff check`.
- **Test role:** tests/fixtures/harness only. Required: `uv run ruff format --check` and targeted `uv run pytest ...`.
- **Integration role:** reconciles code+tests to the spec and must run: `uv run ruff format --check`, `uv run ruff check`, `uv run pytest`, `make smoke`.
- **Docs/tasks/session_log edits live only on the orchestration branch.** Never edit them from worktrees.
- **MCP stdio safety:** no non-JSON-RPC output to stdout once `serve` starts (logs must go to stderr).

## Branch & Worktree Conventions
- Orchestration branch: `feat/browser-orchestration`.
- Task branches: `bo-<triad>-<scope>-<role>` (example: `bo-o1-orchestrator-code`).
- Worktrees: `wt/<branch>` (example: `wt/bo-o1-orchestrator-code`).

## References (architecture decisions)
- `docs/adr/ADR-0001-agent-orchestration-and-answer-contract.md`
- `docs/adr/ADR-0002-operator-dashboard-streaming-and-take-control.md`

## Triad Overview (sized for single-session agents)
This feature is decomposed so each triad is realistically completable by a single agent in one focused session (code/test/integ separately). The highest-risk area (take-control input) is split further.

1. **O1a – Orchestrated `web_eval_agent` (minimal) + JSON response contract**
   - Run browser-use Agent loop and return a stable JSON `TextContent` payload including `session_id`, `status`, `result`, and `summary`.
   - No screenshots, no pause gating, no dev-mode extras.
2. **O1b – Step callbacks + screenshot artifacts + pause gating**
   - Add step hooks for `agent_step` screenshot capture into `ScreenshotManager`.
   - Wire pause gating between steps; keep response compact (references only).

3. **O2a – Run event store (in-memory) + capture pipeline**
   - Add an in-memory event store keyed by `session_id` and record:
     - agent step events (from agent hooks)
     - console + network events (Playwright hooks in our orchestration)
   - Strict bounds and truncation for stored details.
4. **O2b – `get_run_events` tool + response modes (compact vs dev)**
   - Add MCP `get_run_events` with filters and limits.
   - Add `web_eval_agent` response mode selection:
     - `compact` default for non-localhost
     - `dev` default for localhost/127.0.0.1 (bounded console/network excerpts)

5. **O3a – Take-control server API + holder/paused gating**
   - Add `/ctrl` events for browser inputs (click/move/wheel/keydown/keyup/type) and enforce:
     - holder-only
     - paused-only input acceptance
     - rate limiting + security logging on rejects
   - No dashboard JS changes yet; drive via unit tests/fake events.
6. **O3b – CDP input dispatch implementation (keyboard correctness)**
   - Route the input events to the active session via CDP (`Input.dispatch*`).
   - Focus on correctness of keyboard semantics (Enter sequence, modifiers, printable chars), based on `~/web-agent` lessons.
7. **O3c – Dashboard input capture wiring + manual verification steps**
   - Update dashboard JS to capture pointer/keyboard events and emit to `/ctrl`.
   - Add minimal manual verification steps to docs (pause/take-control/typing/clicking/resume).

## Start Checklist (all tasks)
1. `git checkout feat/browser-orchestration && git pull --ff-only`
2. Read this plan, `tasks.json`, `session_log.md`, the triad spec, and your kickoff prompt.
3. Set the task status to `in_progress` in `tasks.json` (on the orchestration branch).
4. Add a START entry to `session_log.md`; commit docs (`docs: start <task-id>`).
5. Create the task branch from `feat/browser-orchestration`; add the worktree: `git worktree add wt/<branch> <branch>`.
6. Do **not** edit docs/tasks/session log within the worktree.

## End Checklist (code/test)
1. Run required commands (code: `uv run ruff format --check`, `uv run ruff check`; test: same + targeted `uv run pytest ...`). Capture outputs.
2. Inside the worktree, commit task changes (no docs updates).
3. Checkout `feat/browser-orchestration`; update `tasks.json` status and add END entry to `session_log.md`; commit docs (`docs: finish <task-id>`).
4. Remove the worktree: `git worktree remove wt/<branch>`.

## End Checklist (integration)
1. Merge code/test branches into the integration worktree; reconcile behavior with the spec.
2. Run `uv run ruff format --check`, `uv run ruff check`, `uv run pytest`, `make smoke`. Capture outputs.
3. Commit integration changes on the integration branch.
4. Fast-forward merge the integration branch into `feat/browser-orchestration`; update `tasks.json` and `session_log.md` with the END entry; commit docs (`docs: finish <task-id>`).
5. Remove the worktree.
