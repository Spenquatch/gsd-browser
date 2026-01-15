# C4 – CDP-first streaming adapter (browser-use sessions)

## Scope
Make streaming frames available during browser-use runs by attaching to the browser-use CDP session manager, not Playwright pages.

### 0) Touchpoints (existing code)
Likely files/entrypoints to inspect and adjust:
- `gsd-browser/src/gsd_browser/streaming/server.py` (Socket.IO `/stream` wiring and streamer lifecycle)
- `gsd-browser/src/gsd_browser/streaming/cdp_screencast.py` (current CDP screencast implementation; currently Playwright-session shaped)
- `gsd-browser/src/gsd_browser/mcp_server.py` (orchestration: where a browser-use run is started and where streaming is hooked)
- `gsd-browser/src/gsd_browser/screenshot_manager.py` (where `stream_sample` should be stored and bounded)
- `docs/adr/ADR-0002-operator-dashboard-streaming-and-take-control.md` (streaming expectations and dashboard behavior)

### 0b) Verified browser-use CDP surface (>= 0.11)
Hardened from DeepWiki review of `browser-use/browser-use`:
- Acquire the focused target session with `await browser_session.get_or_create_cdp_session()` (uses `agent_focus_target_id` when no `target_id` is provided).
- The returned object is a `CDPSession` with:
  - `session_id` (string): must be supplied on CDP commands/events to target the correct page.
  - `cdp_client`: a `CDPClient` that exposes:
    - `send` for CDP commands (typed surface via `cdp_client.send.<Domain>.<method>(..., session_id=...)`), and
    - `register` for CDP event handlers (e.g. `cdp_client.register.Page.screencastFrame(handler)`).
- Event handler signature: `handler(event: dict, cdp_session_id: str | None)` (the CDP client passes the session id as a second argument).

### 1) Streaming adapter
Introduce an adapter that can:
- obtain the focused CDP session via `browser_session.get_or_create_cdp_session(...)`
- start a screencast via `Page.startScreencast`
- receive `Page.screencastFrame` events and ACK each frame via `Page.screencastFrameAck`
- emit frames on the Socket.IO `/stream` namespace
- sample frames into `ScreenshotManager` as `stream_sample` (bounded; existing sampling semantics)

Implementation must use the session-targeted APIs explicitly (no “closest supported API” ambiguity). Concretely:
- Start:
  - `cdp = await browser_session.get_or_create_cdp_session()`
  - Primary (typed): `await cdp.cdp_client.send.Page.startScreencast(params=<quality params>, session_id=cdp.session_id)`
  - Fallback (string): `await cdp.cdp_client.send("Page.startScreencast", <quality params>, session_id=cdp.session_id)`
- On frame:
  - handler receives `params` containing `{ "data": "...base64...", "sessionId": "<ack id>", "metadata": {...} }`
  - handler also receives `cdp_session_id` as a second argument (may be ignored for screencast)
  - `await cdp.cdp_client.send.Page.screencastFrameAck(params={"sessionId": <ack id>}, session_id=cdp.session_id)`
- Stop:
  - `await cdp.cdp_client.send.Page.stopScreencast(session_id=cdp.session_id)`

Fallback rule (explicit):
- If `browser_session.get_or_create_cdp_session` is unavailable or fails, streaming is disabled for that run and the tool must continue without streaming (dashboard can still show screenshots).
- If CDP command send or event registration is not supported by the runtime CDP client, treat that as “CDP unavailable” and disable streaming for the run (do not fall back to Playwright CDP sessions).

### 2) Resilience
Handle:
- detached targets/sessions
- page focus changes during the run
- “no CDP available” fallback (disable streaming; keep the run functional)

### 3) Lifecycle
- Ensure screencast stops when a run ends (success/failure/timeout).
- Ensure a newer run supersedes an older streaming session (no cross-session leaking).

## Acceptance Criteria
1. During a real `web_eval_agent` run, at least one streaming frame is emitted and at least one `stream_sample` is stored (when CDP is available).
2. When CDP cannot attach, the run still completes; streaming is reported as unavailable in stats/artifacts.
3. Unit tests validate:
   - start/stop behavior does not leak tasks
   - sampling bounds and “frame dropped” behavior under backpressure

## Out of Scope
- Run events ranking/reporting (C5).
- Take-control dispatch robustness (C6).
