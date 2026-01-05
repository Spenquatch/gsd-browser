# ADR-0003: CDP-first browser-use integration (streaming, screenshots, events, lifecycle)

## Status
Proposed

## Context
`gsd-browser` is intended to be a practical MCP “browser agent tool”:
- The MCP client calls `web_eval_agent(url, task, ...)` and receives a compact, usable answer plus bounded debugging context.
- Large artifacts (step screenshots, streaming samples, run events) are stored out-of-band and fetched on demand.
- Operators can intervene via a dashboard (stream + true take-control + pause gating).

We have working slices of this vision in `gsd-browser` today (O1a–O3c), but real runs show the experience is not smooth:
- “failed / partial” results often lack actionable “why”.
- Step screenshots are not reliably present (sometimes 0 recorded even after multiple steps).
- Streaming is not consistently available during `browser-use` runs (e.g. `stream_samples: 0` in headless runs).
- Network errors like `net::ERR_BLOCKED_BY_CLIENT` dominate error listings even when they’re not causal.
- Tool timeouts surface at the MCP boundary for real sites.

Separately, the legacy `~/web-eval-agent` repo demonstrates valuable patterns:
- A strong prompt wrapper that sets expectations and stop conditions.
- A step callback that always captures screenshots by directly querying the “current page”.
- A human-friendly report format that prioritizes signal (errors first), then timeline, with truncation.

However, `~/web-eval-agent` used an older integration shape and performed extensive Playwright monkeypatching; `gsd-browser` is built around `browser-use>=0.11`, which is CDP-first. We should lift patterns and UX/reporting choices, not copy the older implementation wholesale.

### Ground truth from browser-use (>=0.11)
From a `browser-use/browser-use` DeepWiki review:
- `Agent.run(...)` supports hooks (`on_step_start`, `on_step_end`) and constructor callbacks (`register_new_step_callback`, `register_done_callback`).
- `BrowserStateSummary` can include a screenshot (base64), but integrations can also reliably capture via the browser-use actor page API.
- `BrowserSession` exposes CDP primitives (`cdp_client`, `get_or_create_cdp_session(...)`) and a session manager that handles target focus/recovery.
- Screencasting in CDP-first mode is done via `Page.startScreencast` and `Page.screencastFrameAck` using the CDP client/session.
- `AgentHistoryList` exposes `final_result()`, `errors()`, `has_errors()`, and judge-related fields that should be used to surface failure reasons.

## Decision
Adopt a CDP-first integration strategy for all “live” runtime behaviors during `web_eval_agent`:
- Treat browser-use `BrowserSession` + actor APIs as the source of truth for:
  - step screenshots
  - streaming frames
  - input dispatch targets (active page/target)
  - run timeline capture
- Avoid Playwright-only hooks and avoid assuming a Playwright `Page` exists or is “the same page” the agent is operating on.
- Make lifecycle ownership explicit: the `Agent` owns starting/stopping the `BrowserSession`; `gsd-browser` should not double-start or leak sessions.

## Consequences
### Positive
- Streaming and screenshots become consistent across headless/non-headless runs because they attach to the same CDP substrate the agent uses.
- Take-control dispatch becomes more robust because it targets the same CDP session manager/focus logic.
- Failure reporting can cite concrete browser-use errors and (optionally) judge outcomes rather than only counts.

### Tradeoffs / Risks
- CDP sessions/targets can detach; we must respect browser-use SessionManager focus semantics and recovery logic.
- Implementing screencast and event capture on CDP requires careful backpressure (queue limits, sampling) to avoid memory growth.
- Some sites employ bot detection; we must treat this as a first-class failure type (and provide operator escape hatches).

## Implementation Notes
This ADR defines required work (design + implementation + validation) to align with CDP-first browser-use.

### 1) Session lifecycle: avoid double-start and ensure cleanup
Current `gsd-browser/src/gsd_browser/mcp_server.py` manually starts a `BrowserSession` before running `Agent.run()`.
In browser-use, `Agent.run()` starts/stops/cleans up the session internally.

Work:
- Remove any explicit `BrowserSession.start()` call in the orchestration path unless browser-use recommends it for a specific integration case.
- Ensure we always call `BrowserSession.stop()`/agent close path via browser-use APIs, even on exceptions/timeouts.
- Add an overall runtime budget and a clear timeout story:
  - tool-level budget (e.g. 45–90s default; configurable)
  - step timeout (`Agent(..., step_timeout=...)`)
  - LLM timeout if supported (`llm_timeout`)
  - `max_steps` tuned for MCP clients (avoid 100 default for typical tool calls).

### 1b) LLM/provider compatibility: make AgentOutput validation reliable
Recent real-world sanity runs surfaced repeated `ModelProviderError` validation failures for `AgentOutput` (missing required `action` field),
even when the agent eventually completes the task. This indicates our current default provider/model combination is not consistently producing
the structured responses browser-use expects.

Work:
- Re-evaluate default `GSD_BROWSER_MODEL` for each provider to ensure it is compatible with browser-use’s output expectations.
- Decide whether to:
  - enforce “known-good” model allowlists per provider (fail fast with actionable error), and/or
  - provide `fallback_llm` so transient structured-output failures can recover without collapsing the whole run.
- Ensure `web_eval_agent` status mapping treats “final_result present + intermittent step errors” as success-with-warnings, not ambiguous partial.

### 2) Step screenshots: guarantee at least N step screenshots per run
Pattern from `~/web-eval-agent`: don’t depend on incidental data; explicitly capture from the current page.

Work:
- In `register_new_step_callback(BrowserStateSummary, AgentOutput, step)`:
  - Primary path: use `BrowserStateSummary.screenshot` when present.
  - Fallback path: `await browser_session.get_current_page()` then `await page.screenshot(format="jpeg", quality=80)` (browser-use actor API), and store it as an `agent_step` screenshot.
- Ensure we always capture at least:
  - step 1 (first observation)
  - last step (on done/failure)
  - plus a bounded max (e.g. keep last 50) to prevent runaway storage.
- Record screenshot metadata: step number, url/title, error flags (including browser-use judgement fields if available).

### 3) Streaming: drive screencast from browser-use CDP sessions, not Playwright pages
Current `gsd-browser` CDP streamer uses `page.context.new_cdp_session(page)` which assumes Playwright pages.
In CDP-first browser-use runs, we should attach streaming to the browser-use CDP session manager.

Work:
- Introduce a CDP streaming adapter that can:
  - obtain a focused `CDPSession` from `browser_session.get_or_create_cdp_session()` (defaults to the current `agent_focus_target_id`)
  - call `Page.startScreencast` on the session’s CDP client
  - register a handler for `Page.screencastFrame` via `cdp_client.register.Page.screencastFrame(handler)` (handler signature includes `cdp_session_id` as a second arg)
  - ACK each frame with `Page.screencastFrameAck`
  - emit frames via Socket.IO (`/stream`) and sample frames into `ScreenshotManager` (`stream_sample`)
- Support pause/resume and teardown:
  - stop screencast when run ends or when a new run becomes active
  - handle detached target/session gracefully (reset, retry with focus recovery).

### 4) Run events: capture timeline using CDP and browser-use events
Current run event capture (`CDPRunEventCapture`) taps internal handler registries; it’s brittle.

Work:
- Prefer browser-use/public CDP registration surfaces (e.g. `cdp_client.register.<Domain>.<event>` when available) and/or browser-use EventBus listeners.
- Capture, bound, and filter:
  - Console: `Runtime.consoleAPICalled`, `Runtime.exceptionThrown`
  - Network: request/response/failed/finished; store URLs and statuses but not bodies
  - Agent: step number, url/title, action summary (from `AgentOutput`), plus “done”/“failure reason”
- Implement an error “signal ranking” layer:
  - de-emphasize noisy endpoints (telemetry, waf beacons) by default
  - highlight likely-causal failures (navigation failures, 4xx/5xx on primary origin XHR, JS exceptions).

### 5) Failure reporting: make `web_eval_agent` “debuggable” in compact mode
Pattern from `~/web-eval-agent`: errors-first presentation, then details, with truncation.

Work:
- In tool response JSON, include:
  - last known url/title
  - top N error messages from `history.errors()` (not just counts)
  - if judge enabled: `judgement().failure_reason`, `reached_captcha`, `impossible_task`
  - a short “what to try next” set (operator control, alternate strategy, re-run with dev mode).
- Consider adding an optional structured output schema mode (Pydantic model) for extraction tasks so results are stable.

### 6) Prompting: adopt web-eval-agent prompt patterns, adapted to browser-use 0.11
Work:
- Create a prompt wrapper that:
  - anchors the agent on the base URL (don’t jump)
  - defines stop conditions (login required, captcha/bot wall)
  - encourages 1–2 retries for transient UI issues
  - requests a final answer in a predictable format (or structured output).
- Implement via browser-use `extend_system_message` / `override_system_message` rather than building bespoke LLM prompts outside browser-use.

### 7) Operator “take control”: ensure inputs always target the active page
O3a–O3c define gating and dispatch; the remaining work is robustness with CDP-first page/target identity.

Work:
- Ensure “active session” corresponds to the browser-use agent focus target, not a stale target ID.
- Ensure pause gating yields a stable window for operator input:
  - when control is taken, auto-pause (policy)
  - when resumed, drain/clear queued input events to avoid accidental replay.

## Open Questions
1. Should we enable browser-use judge mode in `gsd-browser` by default for non-localhost, or keep it opt-in?
2. What is the desired default tool budget (seconds) for MCP clients, and do we allow per-call override?
3. Do we want two streaming modes in production (`cdp` vs screenshot sampling) or always CDP-first?
4. What are the “top 10” real sites we expect this tool to work on without special auth state?

## References
- `docs/adr/ADR-0001-agent-orchestration-and-answer-contract.md`
- `docs/adr/ADR-0002-operator-dashboard-streaming-and-take-control.md`
- `docs/project_management/next/browser-orchestration/plan.md`
- `~/web-eval-agent/webEvalAgent/src/prompts.py` (prompting patterns)
- `~/web-eval-agent/webEvalAgent/src/browser_utils.py` (step screenshot capture pattern)
- DeepWiki review of `browser-use/browser-use` APIs (Agent hooks, BrowserSession CDP access, history errors/judgement, screencast patterns)
