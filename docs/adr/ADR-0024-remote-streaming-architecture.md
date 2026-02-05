# ADR-0024: Remote Streaming Architecture

## Status
Accepted (2026-02-05)

## Context
The current streaming architecture assumes localhost access:
- Dashboard binds to `127.0.0.1:5009` (hardcoded in `runtime.py`)
- Socket.IO clients connect locally
- Frame emission broadcasts to all connected sockets
- No session routing — single active session at a time

For the multi-tenant SaaS product, clients connect remotely to view browser sessions running on cloud workers. Requirements:
- Sub-500ms frame latency from worker to client browser
- Multiple concurrent sessions across multiple workers
- Clients must connect to the correct worker hosting their session
- WebSocket connections must survive load balancer routing

Three options were considered:
1. **Direct WebSocket with session affinity** — workers expose Socket.IO externally, load balancer routes by session
2. **Redis pub/sub relay** — workers publish frames to Redis, a gateway server relays to clients
3. **Media server (WebRTC/HLS)** — workers stream to a media server, clients consume via standard protocols

## Decision

### Option A: Direct WebSocket with session affinity

**Rationale**: At 5-20 concurrent sessions, the simplest architecture wins. Direct WebSocket has the lowest latency (no relay hop), fewest moving parts, and Socket.IO already handles reconnection/fallback. Redis pub/sub adds a relay hop and Redis bandwidth costs. WebRTC/HLS adds significant complexity for JPEG frame streaming that doesn't benefit from media codec optimization.

### 1) Workers expose Socket.IO externally
Workers bind Socket.IO to `0.0.0.0` in production (configurable via `GSD_STREAMING_BIND_HOST`):

```env
GSD_STREAMING_BIND_HOST=0.0.0.0    # Production (accept external connections)
GSD_STREAMING_BIND_HOST=127.0.0.1  # Development (localhost only, default)
```

TLS termination happens at the load balancer (ACA's Envoy proxy), not at the worker.

### 2) Socket.IO rooms per session_id
Replace broadcast frame emission with room-based routing:

- Each session gets a Socket.IO room named by `session_id`
- Clients join a session room after authentication (ADR-0023)
- `CdpScreencastStreamer` emits frames to the session's room, not to all sockets
- A client can be in multiple session rooms simultaneously (e.g., monitoring dashboard)

### 3) `stream_url` in web_eval_agent response
The `web_eval_agent` tool response includes a `stream_url` field pointing to the worker hosting the session:

```json
{
  "job_id": "abc123",
  "session_id": "sess_xyz",
  "stream_url": "https://gsd.example.com"
}
```

- `stream_url` is the **HTTP(S) origin** for the streaming server (no namespace path).
- Clients connect Socket.IO namespaces by appending:
  - `${stream_url}/stream` for frames
  - `${stream_url}/ctrl` for take-control
- In production: `stream_url` resolves to the worker via load balancer session affinity.
- In development: `stream_url` is `http://127.0.0.1:5009` (current behavior).
- The `stream_url` is stable for the lifetime of the session.

### 4) Session affinity via load balancer
ACA's Envoy proxy provides session affinity for WebSocket connections:

- Initial HTTP upgrade request routed to the worker hosting the session
- Affinity key: `session_id` query parameter (preferred) or cookie
- Once upgraded, the WebSocket connection is pinned to the worker
- If the worker restarts, Socket.IO client reconnects and re-routes

### 5) Health check endpoint for session routing
Workers expose a session-aware health endpoint:

```
GET /healthz/sessions/{session_id}
→ 200: session is active on this worker
→ 404: session not found on this worker
```

This enables the load balancer to route session-specific connections to the correct worker. The primary `/healthz` endpoint remains for general liveness checks.

### 6) stream_url construction
The `stream_url` is constructed by the worker at session creation time:

```python
stream_url = f"{scheme}://{public_host}"
```

Where:
- `scheme`: `https` in production, `http` in development
- `public_host`: From `GSD_STREAMING_PUBLIC_HOST` env var (e.g., `gsd.example.com`)
- `session_id`: Passed by clients as a Socket.IO query parameter for load balancer routing

In development, `stream_url` defaults to `http://127.0.0.1:{port}`.

### 7) Worker-embedded combined server (prod shape)
The worker process runs a combined **streaming + health** server on port `5009`:
- Socket.IO namespaces: `/stream` and `/ctrl`
- Health endpoints: `/healthz`, `/healthz/worker`, `/healthz/sessions/{session_id}`

This keeps the runtime topology simple (no extra Container App) and ensures the same
process that owns the browser session also owns the streaming sockets.

## Consequences

### Positive
- Lowest possible latency: direct WebSocket, no relay hop
- Simplest architecture: no additional infrastructure beyond load balancer
- Socket.IO handles reconnection, fallback to polling, and heartbeat natively
- Room-based emission provides natural session isolation
- Works with existing `CdpScreencastStreamer` with minimal changes

### Negative / Costs
- Each worker must be externally reachable (port exposure)
- Session affinity required at load balancer — less flexible than relay architecture
- If a worker dies, active streaming sessions on it are interrupted (client reconnects to a different worker, but session state is lost)
- Horizontal scaling beyond ~50 workers may need a relay layer (acceptable for 5-20 sessions)

## Implementation Notes

### Configuration additions
```env
GSD_STREAMING_BIND_HOST=127.0.0.1        # Bind address (default: localhost)
GSD_STREAMING_PUBLIC_HOST=                 # Public hostname for stream_url construction
GSD_STREAMING_PUBLIC_SCHEME=https          # http or https (default: https in production)
GSD_STREAMING_AUTH_MODE=jwt                # hmac (dev) or jwt (prod)
```

### Frame emission change
```python
# Before (broadcast):
await sio.emit("frame", frame_data, namespace="/stream")

# After (room-scoped):
await sio.emit("frame", frame_data, room=session_id, namespace="/stream")
```

### Client connection flow
1. Client calls `web_eval_agent` (or queries session API) → gets `stream_url`
2. Client connects Socket.IO to `${stream_url}/stream` with JWT auth and `session_id` query param
3. Server validates JWT, extracts identity, checks tenant authorization
4. Client emits `join_session` with `session_id`
5. Server verifies identity is authorized for session, adds socket to room
6. Frames begin streaming to client

### ACA Envoy configuration requirements
- WebSocket upgrade support (enabled by default in ACA)
- Session affinity: cookie-based or header-based (`X-Session-Id`)
- Idle timeout: ≥120 seconds for WebSocket connections (Socket.IO keepalive is 25s)
- Connection draining: allow in-flight WebSocket connections to complete on deploy

### Latency budget
```
CDP screencast → Worker queue:    ~5ms
Worker emit → Envoy proxy:        ~1ms
Envoy → Client (same region):     ~10-50ms
Client decode + render:            ~5-10ms
Total:                             ~20-70ms (well under 500ms target)
```

## Open Questions
None (decisions pinned).

## References
- `docs/adr/ADR-0002-operator-dashboard-streaming-and-take-control.md`
- `docs/adr/ADR-0023-dashboard-auth-for-multi-tenant-remote-access.md`
- `docs/adr/ADR-0025-azure-reference-deployment.md`
- `gsd-browser/src/gsd_browser/streaming/server.py`
- `gsd-browser/src/gsd_browser/streaming/cdp_screencast.py`
- `gsd-browser/src/gsd_browser/runtime.py`
