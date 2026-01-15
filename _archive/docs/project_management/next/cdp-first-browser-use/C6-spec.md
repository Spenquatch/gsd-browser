# C6 – Take-control target robustness (CDP-first)

## Scope
Strengthen take-control so operator inputs always target the active browser-use page/target.

### 0) Touchpoints (existing code)
Likely files/entrypoints to inspect and adjust:
- `gsd-browser/src/gsd_browser/streaming/cdp_input_dispatch.py` (CDP input dispatch path and target selection)
- `gsd-browser/src/gsd_browser/streaming/security.py` (holder-only / paused-only gating and rejection reasons)
- `gsd-browser/src/gsd_browser/streaming/server.py` (Socket.IO control events + pause semantics wiring)
- `gsd-browser/src/gsd_browser/mcp_server.py` (where take-control hooks into the currently active run/session)

### 0b) Verified browser-use focus semantics (>= 0.11)
Hardened from DeepWiki review of `browser-use/browser-use`:
- The focused target is tracked by `BrowserSession` (via `agent_focus_target_id` inside `SessionManager`).
- Use `await browser_session.get_or_create_cdp_session()` to obtain a `CDPSession` for the focused target.
- Dispatching to the wrong target happens when using a root CDP client without a per-target `session_id`; therefore dispatch must be session-scoped.

### 1) Target selection
Ensure CDP input dispatch targets the same focus logic that browser-use uses:
- obtain the active/focused CDP session via browser-use session manager
- avoid dispatching to stale target IDs
- gracefully handle detaches by re-acquiring a focused session (best effort)

Non-ambiguous dispatch rule:
- For every accepted ctrl input event, acquire (or reuse) `cdp_session = await browser_session.get_or_create_cdp_session()` and send `Input.dispatch*` commands via `cdp_session.cdp_client` **with** `session_id=cdp_session.session_id`.
- If a focused `CDPSession` cannot be acquired, reject the input event with a logged reason (`target_unavailable`) rather than dispatching to an arbitrary root client.

### 2) Pause/control policy
Clarify and enforce semantics:
- When an operator takes control, auto-pause the agent (policy configurable; default on).
- While paused, ctrl events are accepted (holder-only rules remain).
- On resume:
  - drain/clear queued input events to prevent accidental replay, or
  - apply only a bounded “recent” window (explicitly specified) if we want to support buffered typing.

### 3) Observability
Record rejected/accepted ctrl input events in run events/security logs with bounds:
- rejected reason (not holder, not paused, rate limited)
- dispatch errors (target detached, invalid payload)

## Acceptance Criteria
1. Ctrl input dispatch uses browser-use focused target/session, not an incidental Playwright page.
2. Taking control reliably pauses the agent, and resuming does not replay stale inputs.
3. Tests validate:
   - holder-only and paused-only gating is preserved
   - target re-acquisition occurs on simulated detaches

## Out of Scope
- Streaming adapter (C4) beyond what is needed for target selection.
