# C1 – Lifecycle + budgets + status mapping

## Scope
### 1) Session lifecycle (no double-start; always cleanup)
- Ensure `web_eval_agent` does **not** explicitly `start()` a `browser-use` `BrowserSession` that the `Agent` is expected to own.
- Ensure cleanup happens on all exit paths (success, failure, timeout, cancellation):
  - agent run finishes
  - exception thrown while creating/starting the agent
  - tool-level timeout
- Ensure MCP stdio safety is preserved (no stdout logging once server starts).

### 2) Timeouts and budgets (predictable; configurable)
Add a clear timeout story with explicit defaults (see plan.md), with per-call overrides:
- tool-level budget (overall wall-clock)
- `max_steps`
- `step_timeout`
- provider-level / request-level timeout if supported by the provider wrapper

### 3) Status mapping semantics (less ambiguous)
Define a stable mapping for `web_eval_agent.status`:
- `success`: `final_result` is present and non-empty
- `failed`: no `final_result` AND we have actionable error(s) (history errors/judgement) OR a timeout
- `partial`: reserved for “result exists but is incomplete/low confidence” **only** when we can explicitly justify it (e.g. judge says `impossible_task` but a partial answer exists)

If browser-use surfaces intermittent step errors (e.g. structured output validation failures) but a final result exists, treat as:
- `success` with warnings surfaced in the response (not `partial`)

## Response Contract (web_eval_agent.v1)
This triad is responsible for making lifecycle + budgets + status mapping deterministic without breaking the existing response shape.

### Invariants (must remain true)
`web_eval_agent` returns a single JSON object with:
- `version`: `gsd-browser.web_eval_agent.v1`
- `session_id`: UUID string (always present; used to fetch artifacts)
- `tool_call_id`: UUID string (always present)
- `url`, `task`, `mode`
- `status`: one of `success` | `partial` | `failed`
- `result`: string or null
- `summary`: bounded string
- `artifacts`: object with counts (`screenshots`, `stream_samples`, `run_events`)
- `next_actions`: list of bounded strings

### Contract deltas (additive; required by C1)
These additions are allowed and should be used to remove ambiguity; they must be optional (clients can ignore them):
- `timeouts`: `{ "budget_s": number, "step_timeout_s": number, "max_steps": number, "timed_out": boolean }`
- `warnings`: list of short strings (bounded; e.g. provider validation errors encountered but recovered)

## Acceptance Criteria
1. `web_eval_agent` no longer double-starts browser-use sessions; the agent owns session start/stop.
2. Tool-level budget and `max_steps`/`step_timeout` defaults are enforced and configurable via tool args.
3. Timeouts/cancellations always produce a single JSON response with:
   - stable `status`
   - an actionable summary of what timed out and what to try next
   - a `session_id` that can be used to retrieve artifacts/events
4. Unit tests validate:
   - the status mapping table
   - timeout behavior produces `failed` with an actionable error

## Out of Scope
- Step screenshot fallback (C3).
- CDP-first streaming (C4).
- Run events and ranked failure reporting (C5).
- Take-control dispatch target robustness (C6).
