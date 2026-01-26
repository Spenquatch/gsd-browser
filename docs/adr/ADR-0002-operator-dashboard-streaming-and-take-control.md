# ADR-0002: Operator dashboard streaming + true “take control”

## Status
Accepted

## Context
`gsd-browser` includes a dashboard with streaming (`/stream`) and control state (`/ctrl`) plus optional auth/rate limiting:
- CDP screencast frames (fast) and screenshot fallback.
- Buttons for Take Control/Release and Pause/Resume (state only).

However, the current dashboard cannot actually “drive” the browser:
- There is no input event routing (mouse/keyboard/scroll) from the dashboard to the active browser session.
- Pause/resume only gates the current stub tool flow, not a full agent step loop.

`~/web-agent` demonstrates the intended operator experience (these capabilities are not present in the upstream `Operative-Sh/web-eval-agent` repo):
- CDP streaming at low latency.
- “Take control” that routes user input to the browser via CDP `Input.dispatch*` events.
- A pause gate that stops the agent from taking further steps while an operator interacts.

We want to preserve the MCP-first behavior (text answer + artifacts on demand), but also provide a robust operator surface for debugging and intervention.

## Decision
Extend the dashboard/control plane in `gsd-browser` to support **true take-control**, meaning:
1. When a dashboard client holds control, it can send input events (click, move, wheel, keydown/keyup, type text).
2. Those events are routed to the *currently active* browser session/page via CDP (preferred), ideally using browser-use’s `BrowserSession` CDP access (`cdp_client` / `get_or_create_cdp_session`) to avoid competing CDP stacks.
3. When paused, the agent orchestration loop must block between steps until resumed.

Security requirements remain mandatory:
- Control plane is gated by existing auth + per-SID rate limiting + nonce handshake when `STREAMING_AUTH_REQUIRED=true`.
- Only the holder SID can send input/control events.

## Consequences
Positive:
- Operators can unblock the agent (login prompts, CAPTCHAs, flaky UI states) without leaving the dashboard.
- Debugging becomes faster because “what the agent sees” and “what the operator does” share the same session.

Tradeoffs / risks:
- Input routing requires careful association between the active session and the dashboard holder (multi-session concurrency).
- CDP input APIs are powerful; strict holder checks and logging are required.
- Must avoid introducing stdout noise that breaks MCP.

## Implementation Notes (non-code)
Implemented architecture:
- A single `ControlState` instance tracks:
  - current holder socket id (`holder_sid`)
  - paused state (`paused`)
  - active run session (`active_session_id`) for routing control input
- Control input events are queued in-memory and drained by the running tool loop which dispatches them
  to the active browser-use CDP session (preferred) via `Input.dispatch*` commands.

Pinned `/ctrl` socket events (current implementation):
- `control_state` (server → client): broadcasts holder/paused/active_session state
- `take_control` / `release_control`
- `pause_agent` / `resume_agent`
- Input events (client → server; queued only when held + paused):
  - `input_click`, `input_move`, `input_wheel`
  - `input_keydown`, `input_keyup`, `input_type`

Pause integration:
- The agent orchestration loop calls `wait_until_unpaused()` between steps.
- Taking control auto-pauses by default (configurable via `GSD_AUTO_PAUSE_ON_TAKE_CONTROL`).

Observability:
- Emit structured security logs on rejected events (non-holder, rate-limited, unauth).
- Provide `/healthz` additions that help ops debug: current holder, paused, active session ids (optional, consider privacy).

## Resolved Questions

### Take control vs pause behavior
**Decision (2026-01-25):** Taking control auto-pauses by default, while still exposing explicit
Pause/Resume controls.

Implementation:
- `GSD_AUTO_PAUSE_ON_TAKE_CONTROL` defaults to `true`.

### Input events while running
**Decision (2026-01-25):** Control input is accepted only when **paused**.

Rationale:
- Prevents operator input and agent actions from racing each other.
- Matches current enforcement (requests are rejected when not paused).

### Multiple concurrent runs with one dashboard instance
**Decision (2026-01-25):** One active session is controllable at a time (single `active_session_id`).

Behavior:
- The most recent run sets the active session for routing control input.
- Concurrent sessions may still stream/record artifacts, but control is routed only to the active one.

## Open Questions
None (control plane behavior pinned).

## References
- Local reference behavior: `~/web-agent/webEvalAgent/src/browser_manager.py` and `~/web-agent/webEvalAgent/src/browser_utils.py` (CDP input dispatch + pause functions)
- Current control plane: `gsd-browser/src/gsd_browser/streaming/server.py`, `gsd-browser/src/gsd_browser/streaming/security.py`, `gsd-browser/src/gsd_browser/streaming/dashboard_static/dashboard.js`
- browser-use CDP/session references: `browser-use/browser-use` (DeepWiki: BrowserSession CDP access via `cdp_client` and `get_or_create_cdp_session`)
