# ADR-0026: Multi-Session Concurrency Model

## Status
Proposed

## Context
The current streaming architecture is designed for a single active session:

- `ControlState` is a singleton holding one `active_session_id`, one `holder_sid`, and one input event queue
- `CdpScreencastStreamer` manages a single CDP screencast attachment (`_cdp_client`, `_active_session_id`)
- `StreamingRuntime` holds one `control_state` and one `cdp_streamer` instance
- `AppRuntime` manages one `DashboardServer` with these singletons
- Frame emission broadcasts to all connected Socket.IO clients

For multi-tenant SaaS (5-20 concurrent sessions on a single worker or across workers), each session needs independent:
- Control state (who holds control, pause state, input events)
- CDP screencast attachment (frame capture from that session's browser)
- Frame routing (emit to authorized viewers of that session only)
- Lifecycle management (create, active, paused, terminated, cleanup)

## Decision

### 1) Replace global singletons with `SessionRegistry`
Introduce a `SessionRegistry` class that maps `session_id → SessionState`:

```python
@dataclass
class SessionState:
    session_id: str
    control: ControlState          # Per-session control state
    streamer: CdpScreencastStreamer # Per-session CDP streamer
    owner_identity: Identity       # Who created this session
    worker_id: str                 # Which worker hosts this session
    status: SessionStatus          # create → active → paused → terminated
    created_at: float
    last_activity_at: float

class SessionRegistry:
    _sessions: dict[str, SessionState]
    _lock: threading.Lock
```

`SessionRegistry` replaces the global `ControlState` singleton and the global `CdpScreencastStreamer` instance. It is owned by `StreamingRuntime`.

### 2) Per-session ControlState
`ControlState` API remains identical but becomes per-session:

- Each `SessionState` contains its own `ControlState` instance
- `holder_sid`, `paused`, `_input_events` are scoped to one session
- `active_session_id` field is removed from `ControlState` (redundant — the session_id is the registry key)
- Thread-safety preserved: each `ControlState` has its own lock

### 3) Per-session CdpScreencastStreamer
`CdpScreencastStreamer` becomes per-session:

- Each `SessionState` contains its own `CdpScreencastStreamer` instance
- The streamer is initialized when a browser session starts (`start_browser_use()`)
- Frame emission targets the session's Socket.IO room (not broadcast)
- Streamer is stopped and cleaned up when the session terminates
- Resource limits: max 20 concurrent streamers per worker (matching max sessions)

### 4) Session lifecycle

```
create → active → paused → terminated → (cleanup)
```

| State | Description |
|-------|-------------|
| `create` | Session allocated, browser not yet launched |
| `active` | Browser running, frames streaming |
| `paused` | Agent paused (take-control or explicit pause) |
| `terminated` | Session complete (success, failure, or timeout) |

Cleanup: After termination, session state is retained for `GSD_SESSION_RETENTION_SECONDS` (default: 3600) for post-mortem viewing, then garbage collected.

### 5) `worker_id` in task ownership records
`TaskOwnershipRecord` gains a `worker_id` field:

```python
class TaskOwnershipRecord(BaseModel):
    # ... existing fields ...
    worker_id: str  # Identifies which worker hosts this session
```

- `worker_id` is set at session creation time (from `GSD_WORKER_ID` env var or hostname)
- Used to construct `stream_url` for remote clients (ADR-0024)
- Stored in Redis alongside other task ownership data

### 6) Tenant session limits
Enforce per-tenant concurrency limits:

```env
GSD_MAX_SESSIONS_PER_TENANT=5  # Default: 5
```

- Checked at `web_eval_agent` invocation time
- Counts active sessions (status: `create` or `active` or `paused`) per `tenant_id`
- Returns a clear error if limit exceeded: "Tenant has N active sessions (limit: M)"
- `gsd:admin` scope is not exempt — limit applies to all tenants

### 7) SessionRegistry API

```python
class SessionRegistry:
    def create_session(self, session_id: str, owner: Identity, worker_id: str) -> SessionState
    def get_session(self, session_id: str) -> SessionState | None
    def get_sessions_by_tenant(self, tenant_id: str) -> list[SessionState]
    def count_active_sessions(self, tenant_id: str) -> int
    def terminate_session(self, session_id: str) -> None
    def cleanup_expired(self) -> int  # Returns number cleaned up
    def all_sessions(self) -> list[SessionState]
```

All methods are thread-safe (internal lock). The registry does not perform I/O — it is a local in-memory data structure. Redis-backed session state (for cross-worker queries) is handled separately via `TaskOwnershipStore`.

### 8) StreamingRuntime changes
`StreamingRuntime` replaces single instances with registry:

```python
@dataclass(frozen=True)
class StreamingRuntime:
    asgi_app: Any
    api_app: FastAPI
    sio: socketio.AsyncServer
    stats: StreamingStats
    screenshots: ScreenshotManager
    registry: SessionRegistry      # Replaces cdp_streamer + control_state
```

Socket.IO event handlers look up the session from the registry:

```python
@sio.on("take_control", namespace="/ctrl")
async def on_take_control(sid, data):
    session_id = data["session_id"]
    session = runtime.registry.get_session(session_id)
    if session is None:
        return {"error": "Session not found"}
    # Authorize + delegate to session.control
    session.control.take(sid)
```

### 9) Management API endpoint
Add `/api/v1/sessions/{session_id}` for session state queries:

```
GET /api/v1/sessions                    → List sessions (tenant-scoped)
GET /api/v1/sessions/{session_id}       → Session details + status
DELETE /api/v1/sessions/{session_id}    → Terminate session
```

Responses include: session_id, status, owner (tenant_id, subject_id), worker_id, stream_url, created_at, last_activity_at.

## Consequences

### Positive
- Enables concurrent sessions on a single worker (5-20 range)
- Clean separation of per-session state eliminates race conditions between sessions
- `ControlState` API unchanged — take-control logic works per-session without modification
- Registry pattern is simple and testable
- Session lifecycle enables resource cleanup and monitoring

### Negative / Costs
- Memory scales linearly with sessions: each session holds a `CdpScreencastStreamer` + `ControlState` + frame queue
- All existing code that accesses `runtime.control_state` or `runtime.cdp_streamer` must be updated to go through the registry
- Socket.IO event handlers need `session_id` in every event payload (currently implicit)
- Testing requires multi-session fixtures

## Implementation Notes

### Migration strategy
1. Create `SessionRegistry` class with full API
2. Refactor `ControlState` — remove `active_session_id`, keep rest unchanged
3. Refactor `CdpScreencastStreamer` — accept session_id at init, emit to room not broadcast
4. Update `StreamingRuntime` — replace `control_state` + `cdp_streamer` with `registry`
5. Update Socket.IO handlers — add `session_id` to event payloads, look up session from registry
6. Update `web_eval_agent` — create session via registry, enforce tenant limits
7. Add session management HTTP endpoints

### Backward compatibility
- Single-session localhost usage continues to work — registry just has one entry
- Socket.IO clients that don't send `session_id` in events get the most recent active session (deprecated, with warning log)

### Resource cleanup
```python
async def _cleanup_loop(registry: SessionRegistry, interval_s: int = 60):
    while True:
        await asyncio.sleep(interval_s)
        cleaned = registry.cleanup_expired()
        if cleaned:
            logger.info("Cleaned up %d expired sessions", cleaned)
```

### Thread safety
- `SessionRegistry._lock` protects the `_sessions` dict
- Individual `ControlState` instances have their own locks (no global lock contention)
- `CdpScreencastStreamer` is single-session, no internal locking changes needed
- Frame emission is async (via Socket.IO rooms), no blocking

## Open Questions
None (decisions pinned).

## References
- `docs/adr/ADR-0002-operator-dashboard-streaming-and-take-control.md`
- `docs/adr/ADR-0023-dashboard-auth-for-multi-tenant-remote-access.md`
- `docs/adr/ADR-0024-remote-streaming-architecture.md`
- `gsd-browser/src/gsd_browser/streaming/server.py` — `ControlState`, `StreamingRuntime`
- `gsd-browser/src/gsd_browser/streaming/cdp_screencast.py` — `CdpScreencastStreamer`
- `gsd-browser/src/gsd_browser/runtime.py` — `AppRuntime`
- `gsd-browser/src/gsd_browser/optionb/task_ownership.py` — `TaskOwnershipRecord`
