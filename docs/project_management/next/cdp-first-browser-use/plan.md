# CDP-first browser-use Integration Feature Plan

## Purpose
Make `web_eval_agent` consistently debuggable and operator-friendly by aligning all “live” runtime behavior to `browser-use>=0.11`’s CDP-first substrate:
- reliable step screenshots (non-zero, bounded)
- reliable streaming frames during browser-use runs (headless included)
- run events that surface actionable failures (errors-first, ranked)
- explicit, safe lifecycle ownership (no double-start; no leaked sessions)
- predictable prompting + stop conditions (bot wall/login/captcha)
- take-control inputs always target the active browser-use page/target

This plan is the implementation pack for `docs/adr/ADR-0003-cdp-first-browser-use-integration.md`.

## Guardrails
- **Triads only:** every slice ships as code / test / integration. No mixed commits.
- **Code role:** production Python only (no tests). Required commands from the worktree: `uv run ruff format --check`, `uv run ruff check`.
- **Test role:** tests/fixtures/harness only. Required: `uv run ruff format --check` and targeted `uv run pytest ...`.
- **Integration role:** reconciles code+tests to the spec and must run: `uv run ruff format --check`, `uv run ruff check`, `uv run pytest`, `make smoke`.
- **Docs/tasks/session_log edits live only on the orchestration branch.** Never edit them from worktrees.
- **MCP stdio safety:** no stdout output once `serve` starts (logs must go to stderr).

## Branch & Worktree Conventions
- Orchestration branch: `feat/cdp-first-browser-use`.
- Task branches: `cf-<triad>-<scope>-<role>` (example: `cf-c3-screenshots-code`).
- Worktrees: `wt/<branch>` (example: `wt/cf-c3-screenshots-code`).

## References
- `docs/adr/ADR-0003-cdp-first-browser-use-integration.md`
- `docs/adr/ADR-0001-agent-orchestration-and-answer-contract.md`
- `docs/adr/ADR-0002-operator-dashboard-streaming-and-take-control.md`
- `docs/project_management/next/browser-orchestration/plan.md` (current O1–O3 baseline)
- `gsd-browser/src/gsd_browser/mcp_server.py` (current web_eval_agent orchestration)
- `gsd-browser/src/gsd_browser/streaming/cdp_screencast.py` (Playwright-based streamer to replace/augment)
- `gsd-browser/src/gsd_browser/run_event_capture.py` (current brittle CDP capture)

## Defaults (explicit, changeable)
These defaults are used in specs unless overridden:
- Tool budget: 60s default, configurable per call.
- `max_steps`: 25 default, configurable per call.
- `step_timeout`: 15s default, configurable per call.
- Judge mode: opt-in (default off) until we have stable provider/model coverage.
- Streaming: CDP-first where possible; fall back to screenshot mode if CDP cannot attach.

## Non-ambiguous browser-use surfaces (>= 0.11)
These API surfaces are the assumed “source of truth” for C4/C5/C6 and are referenced explicitly in the triad specs:
- Focused target CDP session: `await BrowserSession.get_or_create_cdp_session()` (defaults to `agent_focus_target_id` when no `target_id` is provided).
- Session object: `CDPSession` with `session_id` + `cdp_client`.
- CDP commands: `await cdp_client.send.<Domain>.<method>(..., session_id=cdp_session.session_id)`.
- CDP events: `cdp_client.register.<Domain>.<event>(handler)` where handler signature is `handler(event, cdp_session_id)`.

## Triad Overview
1. **C1 – Lifecycle + budgets + status mapping**
   - Remove double-start of `BrowserSession`, enforce cleanup, and make timeouts predictable.
2. **C2 – Provider compatibility + prompt wrapper**
   - Reduce `AgentOutput` validation failures via explicit provider/model policy and a browser-use-native prompt wrapper.
3. **C3 – Step screenshots guarantee (CDP-first fallback)**
   - Ensure step screenshots are recorded even when `BrowserStateSummary` has no screenshot payload.
4. **C4 – CDP-first streaming adapter (browser-use sessions)**
   - Stream from `BrowserSession.get_or_create_cdp_session(...)`, not Playwright `Page`.
5. **C5 – Run events + ranked failure reporting**
   - Capture console/network timeline robustly and make compact `web_eval_agent` responses debuggable.
6. **C6 – Take-control target robustness**
   - Ensure ctrl inputs always dispatch to the browser-use active target; strengthen pause/queue semantics.

## Start Checklist (all tasks)
1. `git checkout feat/cdp-first-browser-use && git pull --ff-only`
2. Read this plan, `tasks.json`, `session_log.md`, the triad spec, and your kickoff prompt.
3. Set the task status to `in_progress` in `tasks.json` (on the orchestration branch).
4. Add a START entry to `session_log.md`; commit docs (`docs: start <task-id>`).
5. Create the task branch from `feat/cdp-first-browser-use`; add the worktree: `git worktree add wt/<branch> <branch>`.
6. Do **not** edit docs/tasks/session log within the worktree.

## End Checklist (code/test)
1. Run required commands (code: `uv run ruff format --check`, `uv run ruff check`; test: same + targeted `uv run pytest ...`). Capture outputs.
2. Inside the worktree, commit task changes (no docs updates).
3. Checkout `feat/cdp-first-browser-use`; update `tasks.json` status and add END entry to `session_log.md`; commit docs (`docs: finish <task-id>`).
4. Remove the worktree: `git worktree remove wt/<branch>`.

## End Checklist (integration)
1. Merge code/test branches into the integration worktree; reconcile behavior with the spec.
2. Run `uv run ruff format --check`, `uv run ruff check`, `uv run pytest`, `make smoke`. Capture outputs.
3. Commit integration changes on the integration branch.
4. Fast-forward merge the integration branch into `feat/cdp-first-browser-use`; update `tasks.json` and `session_log.md` with the END entry; commit docs (`docs: finish <task-id>`).
5. Remove the worktree.
