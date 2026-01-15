# A2 — Pre-teardown artifact guarantees

## Scope
Guarantee that at least one step screenshot is captured even when runs abort early (before browser-use session teardown).

### Requirements
- Capture screenshot while the browser session is still alive, using a browser-use hook that runs before teardown:
  - preferred: done callback (`register_done_callback`), and/or
  - step end hook (`on_step_end`) when available.
- Ensure “guarantee capture” does not depend on post-teardown “current page” availability.
- Keep the change minimal: only the screenshot guarantee timing/placement changes in this triad.

## Acceptance criteria
1. Deterministic tests simulate an early abort path and assert:
   - at least one `agent_step` screenshot recorded
2. The real-world sanity harness no longer reports `screenshots=0` for common early-abort failures when a page was reachable.

## Out of scope
- Prompt wrapper content changes (A1).
- Recording new run event types or changing failure ranking (A3).
- Harness classification changes (A4).
