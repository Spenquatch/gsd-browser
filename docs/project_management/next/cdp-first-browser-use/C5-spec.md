# C5 – Run events + ranked failure reporting

## Scope
### 1) Run event capture (robust registration)
Replace brittle CDP handler monkeypatching with supported registration surfaces:
- Prefer browser-use/public CDP registration mechanisms (domain event listeners) when available.
- Capture bounded, privacy-respecting events:
  - Console: `Runtime.consoleAPICalled`, `Runtime.exceptionThrown`
  - Network: request/response/failed/finished (URLs/status/duration only; no bodies)
  - Agent: step number, url/title, and action summary (from `AgentOutput`), plus done/failure summary

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
- optional `judge` fields when available (failure_reason, captcha flags)
- `next_actions`: suggested follow-ups (e.g., run `get_run_events`, run in dev mode, take control)

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
