# ADR-0023: Dashboard Auth for Multi-Tenant Remote Access

## Status
Proposed

## Context
The streaming dashboard currently uses HMAC-SHA256 nonce authentication (ADR-0002, `streaming/security.py`). This works well for localhost single-user scenarios:

1. Client requests nonce via `/auth/nonce`
2. Client computes `hmac.sha256(api_key, nonce)`
3. Server validates signature and allows Socket.IO connection

For multi-tenant remote access, HMAC nonce auth is insufficient:
- The shared `STREAMING_API_KEY` cannot identify individual users or tenants
- Frame emission is broadcast to all connected sockets — no tenant isolation
- No integration path with external identity providers (Clerk, Auth0, etc.)
- The nonce endpoint is unauthenticated, relying on API key secrecy

The MCP HTTP transport already uses JWT validation via `GsdJwtVerifier` (ADR-0013). The dashboard streaming server should use the same verification infrastructure for production deployments.

## Decision

### 1) Add `auth_mode` to `StreamingAuthConfig`
`StreamingAuthConfig` gains an `auth_mode` field:

```python
auth_mode: Literal["hmac", "jwt"] = "hmac"
```

- `hmac` (default): Current HMAC nonce flow. Used for localhost dev, backward compatible.
- `jwt`: JWT validation using `GsdJwtVerifier`. Used for production multi-tenant deployments.

Configured via `GSD_STREAMING_AUTH_MODE` environment variable.

### 2) JWT validation for Socket.IO connections
When `auth_mode == "jwt"`, the Socket.IO `connect` handler validates JWTs:

```python
# Socket.IO auth payload
auth = { "token": "<JWT>" }
```

Validation flow:
1. Extract `token` from Socket.IO `auth` dict
2. Pass to `GsdJwtVerifier.verify_token()` (same instance as MCP HTTP)
3. Extract `Identity` from token claims via `identity_from_claims()`
4. Store `sid → Identity` mapping in `StreamingRuntime`
5. Reject connection on validation failure with appropriate error

### 3) sid → Identity mapping
`StreamingRuntime` maintains a mapping from Socket.IO session IDs to verified identities:

```python
_sid_identity: dict[str, Identity] = {}
```

- Populated on successful `connect` (JWT mode)
- Removed on `disconnect`
- Queried for authorization checks on every event and frame emission

In HMAC mode, all sids map to `STDIO_IDENTITY` (local/local) for backward compatibility.

### 4) Identity-scoped frame emission
Frame emission becomes identity-aware:

- Each session has an owner identity (from the `web_eval_agent` caller)
- Frames for a session are only emitted to sockets whose identity matches the session owner's `tenant_id`
- Implementation: Socket.IO rooms per `session_id`, sockets join rooms based on tenant authorization
- A socket can view sessions owned by their tenant (same `tenant_id`)
- `gsd:admin` scope bypasses tenant restriction (can view all sessions)

### 5) JWT middleware for HTTP endpoints
Streaming server HTTP endpoints (`/api/v1/sessions/*`, `/healthz`) gain JWT middleware when `auth_mode == "jwt"`:

- `/healthz`: No auth required (load balancer health checks)
- `/auth/nonce`: Disabled in JWT mode (returns 404)
- `/api/v1/*`: Requires valid JWT in `Authorization: Bearer <token>` header
- Identity extracted and passed to endpoint handlers for tenant-scoped queries

### 6) HMAC remains the default for backward compatibility
- `auth_mode` defaults to `"hmac"` — no breaking changes for existing localhost users
- HMAC mode behavior is unchanged: nonce endpoint, signature validation, broadcast emission
- Production deployments set `GSD_STREAMING_AUTH_MODE=jwt` along with JWT configuration

## Consequences

### Positive
- Reuses existing `GsdJwtVerifier` — no new auth infrastructure
- Tenant isolation for frame streaming — users only see their own sessions
- Same JWT works for MCP HTTP and dashboard streaming — single token, single identity
- HMAC fallback preserves localhost dev experience

### Negative / Costs
- Two auth code paths to maintain (HMAC and JWT)
- JWT mode requires `GsdJwtVerifier` configuration (JWKS URI, audience, etc.)
- Socket.IO reconnection must refresh JWT if token expires during session

## Implementation Notes

### StreamingAuthConfig changes
```python
class StreamingAuthConfig:
    auth_mode: Literal["hmac", "jwt"] = "hmac"
    # Existing HMAC fields preserved:
    auth_required: bool = False
    api_key: str | None = None
    nonce_ttl: int = 60
    nonce_uses: int = 4
    # JWT mode fields:
    jwt_verifier: GsdJwtVerifier | None = None  # Injected at startup
```

### Socket.IO connect handler (JWT mode)
```python
@sio.on("connect", namespace="/stream")
async def on_stream_connect(sid, environ, auth):
    if config.auth_mode == "jwt":
        token = (auth or {}).get("token")
        if not token:
            raise ConnectionRefusedError("Missing token")
        access_token = await config.jwt_verifier.verify_token(token)
        if access_token is None:
            raise ConnectionRefusedError("Invalid token")
        identity = identity_from_claims(access_token.claims, ...)
        runtime._sid_identity[sid] = identity
    elif config.auth_mode == "hmac":
        # Existing HMAC validation
        ...
```

### Frame emission scoping
```python
async def emit_frame(session_id: str, frame_data: dict):
    # Emit to session room only (sockets that joined this session's room)
    await sio.emit("frame", frame_data, room=session_id, namespace="/stream")
```

Socket room join authorization:
```python
@sio.on("join_session", namespace="/stream")
async def on_join_session(sid, data):
    session_id = data.get("session_id")
    identity = runtime._sid_identity.get(sid)
    session_owner = registry.get_session_owner(session_id)
    if identity.tenant_id == session_owner.tenant_id or has_admin_scope(sid):
        sio.enter_room(sid, session_id, namespace="/stream")
    else:
        await sio.emit("error", {"message": "Access denied"}, to=sid)
```

### Security logging
All auth events in JWT mode logged to `security.log`:
- `jwt_auth_success`: sid, tenant_id, subject_id
- `jwt_auth_failure`: sid, reason (expired, bad signature, missing claims)
- `session_join_denied`: sid, session_id, tenant_id mismatch

### Migration path
1. Deploy with `GSD_STREAMING_AUTH_MODE=hmac` (current behavior)
2. Configure JWT settings alongside HMAC
3. Switch to `GSD_STREAMING_AUTH_MODE=jwt` when React dashboard is deployed
4. Remove HMAC code path in a future release (optional)

## Open Questions
None (decisions pinned).

## References
- `docs/adr/ADR-0002-operator-dashboard-streaming-and-take-control.md`
- `docs/adr/ADR-0013-mcp-compliant-http-authorization-surfaces-and-scope-model.md`
- `docs/adr/ADR-0022-clerk-identity-integration.md`
- `gsd-browser/src/gsd_browser/streaming/security.py`
- `gsd-browser/src/gsd_browser/optionb/identity.py`
