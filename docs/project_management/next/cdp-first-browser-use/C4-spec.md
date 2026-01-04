# C4 – CDP-first streaming adapter (browser-use sessions)

## Scope
Make streaming frames available during browser-use runs by attaching to the browser-use CDP session manager, not Playwright pages.

### 1) Streaming adapter
Introduce an adapter that can:
- obtain an active CDP session from `BrowserSession.get_or_create_cdp_session(focus=True)` (or closest supported API)
- start a screencast (`Page.startScreencast`) via that session
- receive `Page.screencastFrame` events and ACK each frame (`Page.screencastFrameAck`)
- emit frames on the Socket.IO `/stream` namespace
- sample frames into `ScreenshotManager` as `stream_sample` (bounded; existing sampling semantics)

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

