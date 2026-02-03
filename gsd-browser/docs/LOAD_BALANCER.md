# Load Balancer Requirements for Remote Streaming

This document covers the load balancer configuration needed to deploy GSD browser streaming behind a reverse proxy / load balancer such as Azure Container Apps (Envoy), Nginx, or Traefik.

## Architecture Overview

Each GSD worker runs a Socket.IO server that streams browser frames to connected clients. Clients connect via WebSocket to the worker hosting their specific session. The load balancer must route WebSocket connections to the correct backend worker based on session affinity.

```
Client ──WebSocket──> Load Balancer ──affinity──> Worker (Socket.IO)
```

## Requirements

### 1. WebSocket Upgrade Support

The load balancer **must** support HTTP/1.1 → WebSocket upgrade for Socket.IO connections:

- Path: `/socket.io/` (Socket.IO's default transport path)
- Protocols: `websocket` and `polling` (Socket.IO starts with polling, upgrades to WebSocket)
- The `Upgrade: websocket` and `Connection: Upgrade` headers must be forwarded

**Azure Container Apps**: WebSocket upgrade is enabled by default.

### 2. Session Affinity (Sticky Sessions)

Socket.IO connections for a given browser session must route to the worker hosting that session. Two affinity strategies are supported:

**Option A — Cookie-based affinity** (recommended for ACA):
- ACA's built-in sticky sessions use a cookie (`SERVERID` or custom)
- The initial Socket.IO polling request establishes affinity; subsequent requests and the WebSocket upgrade follow the same route

**Option B — Header/query-based routing**:
- Clients include `session_id` as a query parameter: `/socket.io/?session_id=<id>`
- The load balancer routes based on this parameter to the worker that owns the session
- Requires custom routing rules (e.g., Envoy route match on query parameter)

### 3. Health Check Endpoints

Two health check endpoints are available:

| Endpoint | Purpose | Expected Response |
|----------|---------|-------------------|
| `GET /healthz` | General liveness | `200 {"status": "ok"}` |
| `GET /healthz/worker` | Worker identity + session count | `200 {"worker_id": "...", "active_sessions": N, ...}` |

Configure the load balancer health check to use `GET /healthz` with:
- Interval: 10-15 seconds
- Timeout: 5 seconds
- Unhealthy threshold: 3 consecutive failures

### 4. Timeout Configuration

| Setting | Minimum | Recommended | Reason |
|---------|---------|-------------|--------|
| WebSocket idle timeout | 60s | 120s | Socket.IO keepalive ping is 25s |
| HTTP request timeout | 30s | 60s | Socket.IO long-polling requests |
| Connection draining | 30s | 60s | Allow in-flight WebSocket connections to complete on deploy |

Socket.IO sends a ping every 25 seconds by default; set the idle timeout above this to prevent premature disconnection.

### 5. TLS Termination

- TLS should terminate at the load balancer, not at the worker
- Workers bind to `0.0.0.0` over plain HTTP (set `GSD_STREAMING_BIND_HOST=0.0.0.0`)
- The load balancer presents the TLS certificate and proxies to backend over HTTP
- `stream_url` uses `wss://` scheme in production (`GSD_STREAMING_PUBLIC_SCHEME=wss`)

### 6. CORS / Origin Headers

If the React dashboard is served from a different origin than the streaming API:

- The load balancer should forward `Origin` headers to the backend
- Configure `STREAMING_ALLOWED_ORIGINS` on the worker to include the dashboard origin
- Socket.IO handles CORS at the application level via its `cors` configuration

## Configuration Reference

### Worker Environment Variables

```env
# Bind to all interfaces (required for external access)
GSD_STREAMING_BIND_HOST=0.0.0.0

# Public-facing hostname for stream_url construction
GSD_STREAMING_PUBLIC_HOST=gsd.example.com

# URL scheme for stream_url (ws or wss)
GSD_STREAMING_PUBLIC_SCHEME=wss

# Streaming port (default: 5009)
GSD_STREAMING_PORT=5009

# JWT auth mode for production
GSD_STREAMING_AUTH_MODE=jwt

# CORS origins (comma-separated)
STREAMING_ALLOWED_ORIGINS=https://dashboard.example.com
```

### Azure Container Apps (ACA) Specifics

ACA uses Envoy proxy with these defaults:
- WebSocket support: **enabled** (no extra config needed)
- Session affinity: Enable via `ingress.stickySessions.affinity: cookie`
- Idle timeout: Default is 240s (sufficient for Socket.IO)
- Max connections per replica: Monitor via container metrics

Example ACA ingress snippet (Bicep):
```bicep
ingress: {
  external: true
  targetPort: 5009
  transport: 'http'
  stickySessions: {
    affinity: 'sticky'
  }
}
```

### Nginx Example

```nginx
upstream gsd_workers {
    ip_hash;  # or use sticky cookie
    server worker-1:5009;
    server worker-2:5009;
}

server {
    listen 443 ssl;
    server_name gsd.example.com;

    location /socket.io/ {
        proxy_pass http://gsd_workers;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 120s;
        proxy_send_timeout 120s;
    }

    location / {
        proxy_pass http://gsd_workers;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## Latency Budget

```
CDP screencast → Worker queue:    ~5ms
Worker emit → Load balancer:      ~1ms
Load balancer → Client (same AZ): ~10-50ms
Client decode + render:           ~5-10ms
Total:                            ~20-70ms
```

Target: <500ms end-to-end. The direct WebSocket architecture (no relay) stays well within this budget.

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Frequent disconnects (every 25-60s) | WebSocket idle timeout too low | Increase LB idle timeout to 120s+ |
| Socket.IO stuck on polling (no upgrade) | WebSocket upgrade not forwarded | Ensure `Upgrade` / `Connection` headers are proxied |
| Client connects but no frames | Wrong worker (no affinity) | Enable sticky sessions / session affinity |
| 502/504 on WebSocket upgrade | Backend not reachable | Check `GSD_STREAMING_BIND_HOST=0.0.0.0` |
| CORS errors in browser | Origin not allowed | Add dashboard origin to `STREAMING_ALLOWED_ORIGINS` |
