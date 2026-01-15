# C5 – Run events + ranked failure reporting

## Scope
### 0) Touchpoints (existing code)
Likely files/entrypoints to inspect and adjust:
- `gsd-browser/src/gsd_browser/run_event_capture.py` (current CDP capture; currently wraps handler registries)
- `gsd-browser/src/gsd_browser/run_event_store.py` (bounds, filtering, and retrieval APIs used by `get_run_events`)
- `gsd-browser/src/gsd_browser/mcp_server.py` (where `web_eval_agent` assembles the compact response JSON)
- `docs/adr/ADR-0001-agent-orchestration-and-answer-contract.md` (answer contract fields; keep additions backward compatible)
- `docs/adr/ADR-0002-operator-dashboard-streaming-and-take-control.md` (operator-facing debug expectations)

### 0b) Verified browser-use CDP event registration surface (>= 0.11)
Hardened from DeepWiki review of `browser-use/browser-use`:
- CDP events should be subscribed via `cdp_client.register.<Domain>.<event>(handler)` rather than by mutating private handler registries.
- Obtain the currently focused target session via `await browser_session.get_or_create_cdp_session()` and subscribe on that session’s `cdp_client`.
- Focus changes/detaches are managed by browser-use `SessionManager`; re-acquire a focused `CDPSession` and re-attach listeners when needed.
- Event handler signature: `handler(event: dict, cdp_session_id: str | None)` (the CDP client passes the session id as a second argument).

### 1) Run event capture (robust registration)
Replace brittle CDP handler monkeypatching with supported registration surfaces:
- Use `cdp_client.register` domain event listeners as the primary mechanism.
- Capture bounded, privacy-respecting events:
  - Console: `Runtime.consoleAPICalled`, `Runtime.exceptionThrown`
  - Network: request/response/failed/finished (URLs/status/duration only; no bodies)
  - Agent: step number, url/title, and action summary (from `AgentOutput`), plus done/failure summary

Explicit subscription list (no ambiguity):
- Console:
  - `Runtime.consoleAPICalled`
  - `Runtime.exceptionThrown`
- Network:
  - `Network.requestWillBeSent`
  - `Network.responseReceived`
  - `Network.loadingFinished`
  - `Network.loadingFailed`

If the typed `cdp_client.register` surface is not available in the runtime CDP client, fallback behavior is:
- Keep the existing `CDPRunEventCapture` wrapper approach (private handler registry) until the dependency is upgraded, but do not add any new private-hook dependencies beyond what already exists today.

### 2) Error signal ranking (errors-first)
Implement an “error signal ranking” layer used by:
- `web_eval_agent` compact responses
- `get_run_events` (dev mode excerpts)

Ranking goals:
- de-emphasize common noise (telemetry, WAF beacons) by default
- highlight likely-causal failures:
  - navigation failures
  - primary-origin 4xx/5xx XHR/fetch
  - JS exceptions that occur near the failure step
  - explicit browser-use “judge” failures (when enabled)

### 3) Make compact responses debuggable
In the `web_eval_agent` JSON response, include bounded failure context:
- `page`: last known `url` + `title`
- `errors_top`: top N (default 5–10) ranked error summaries
- optional `judge` fields (only if judge mode is enabled and values are present; e.g. `failure_reason`, captcha flags)
- `next_actions`: suggested follow-ups (e.g., run `get_run_events`, run in dev mode, take control)

## Contract deltas (web_eval_agent.v1; additive)
These fields must be optional and bounded:
- `page`: `{ "url": string | null, "title": string | null }` (best-effort, last known)
- `errors_top`: list of `{ "type": "console" | "network" | "agent" | "judge", "summary": string, "step": number | null, "url": string | null }`
- `warnings`: list of short strings (can be set by C1/C2/C3/C4 to surface recoverable issues)

## Acceptance Criteria
1. `get_run_events` and compact tool responses consistently include actionable errors (not just counts).
2. Noisy `net::ERR_BLOCKED_BY_CLIENT` events are not presented as top-causal by default.
3. Tests validate:
   - event storage bounds and truncation
   - ranking behavior for a small fixed fixture set
   - response JSON includes `errors_top` and `page` fields on failure

## Out of Scope
- Provider/model policy and prompting (C2).
- Streaming adapter (C4).
- Take-control dispatch robustness (C6).
