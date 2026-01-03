# O2a – Run event store (in-memory) + capture pipeline

## Scope
- Add an in-memory run event store keyed by `session_id` that can record:
  - Agent step events (step number, goal/action summary, timestamps).
  - Console events (type, message, location, timestamp) – bounded/truncated.
  - Network events (method, url/path, status, timing) – bounded/truncated.
- Event capture sources:
  - Agent callbacks from browser-use for agent step lifecycle.
  - Playwright page hooks in our orchestration layer for console/network.
- Hard limits:
  - Max events per session per type.
  - Max string length per field (truncate with indicator).
  - Avoid storing response bodies by default.

## Acceptance Criteria
1. Event store records agent/console/network events during a run (verified via unit tests with injected events).
2. Limits and truncation are enforced deterministically.
3. `web_eval_agent` updates its `artifacts` counts to reflect stored run event counts (even before `get_run_events` exists).
4. No changes to MCP surface area yet (tool added in O2b).

## Out of Scope
- `get_run_events` tool (O2b).
- Dev/compact response modes (O2b).

