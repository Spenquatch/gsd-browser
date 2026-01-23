# ADR-0014: Local HTTP security hardening model

## Status
Accepted

## Context
`gsd` can be run as a local HTTP MCP server (Streamable HTTP) for developer convenience and for MCP
hosts that prefer an HTTP daemon over stdio subprocesses.

Even on “localhost”, an HTTP service has a different threat model than stdio:
- DNS rebinding and other origin-confusion attacks can target loopback services via a browser.
- Web pages can trigger cross-origin requests (CSRF-ish patterns) to localhost services.
- Secrets (bearer tokens, cookies, headers) can leak via logs if not handled carefully.

The MCP security guidance expects local HTTP deployments to include baseline hardening measures.

## Decision

### 1) Bind to localhost by default
Default the HTTP server bind address to loopback (e.g., `127.0.0.1`) unless explicitly configured
otherwise.

### 2) Validate `Origin` for browser-reachable requests
Enforce a configurable origin allowlist policy for local deployments with opt-in support for
development tools and file:// origins.

**Origin validation policy:**
- **Default allowlist:** `http://localhost`, `http://127.0.0.1`, `http://[::1]` (all ports)
- **Configurable allowlist:** `GSD_HTTP_ALLOWED_ORIGINS` environment variable (comma-separated list)
- **Null origin support:** `GSD_HTTP_ALLOW_NULL_ORIGIN=true` flag for file:// access (default: false)
- **Validation scope:** Applied to specific endpoint classes (see section 6 below)

**Allowed origins configuration:**
```bash
# Default (strict localhost only)
# GSD_HTTP_ALLOWED_ORIGINS not set → uses default: localhost, 127.0.0.1, [::1]

# Custom origins (for development tools, reverse proxies)
GSD_HTTP_ALLOWED_ORIGINS="http://localhost,http://127.0.0.1,http://dev.example.com:3000"

# Allow null origin for file:// protocol access
GSD_HTTP_ALLOW_NULL_ORIGIN=true
```

**Rejection behavior:**
- Requests with missing or disallowed origins are rejected with `403 Forbidden`
- Error response includes: `{"error": "origin_not_allowed", "origin": "<origin>"}`

**Security warnings:**
- Null origin can be spoofed by attackers; only enable for trusted local development
- Document DNS rebinding risks in `docs/SECURITY.md`
- Operators should use minimal allowlists in production

**Rationale:** Local development requires flexibility for tools like Postman, browser extensions, and
file:// based access. Default to strict localhost origins, but allow explicit opt-in via configuration
with documented security warnings. Balances security hardening with developer convenience.

### 3) Validate `Host` / forwarded host in local-hardening mode
To strengthen DNS rebinding defenses beyond `Origin` checks:
- validate `Host` (and, when applicable, `X-Forwarded-Host`) against an allowlist in local-hardening
  mode,
- default allowlist includes `localhost`, `127.0.0.1`, and `[::1]` unless explicitly configured.

### 4) Redact secrets from logs
Never log secrets:
- redact `Authorization` and other sensitive headers by default,
- ensure structured logs/events do not capture bearer tokens or credential material.

### 5) Treat CORS as an explicit opt-in
Do not enable permissive CORS by default. If CORS is needed for a deployment, it must be explicitly
configured and documented with a narrow allowlist.

### 6) Origin validation scope (endpoint classification)
Apply origin validation selectively based on endpoint security requirements.

**Exempt endpoints (no origin validation):**
- `GET /.well-known/*` - OAuth/MCP metadata discovery (must be publicly accessible)
- `GET /health` - Health check endpoint
- `OPTIONS *` - CORS preflight requests

**Validated endpoints (origin validation required):**
- `POST /mcp` - MCP protocol tool execution
- `PUT /mcp` - MCP protocol updates
- `DELETE /mcp` - MCP protocol deletions
- `/api/*` - All API endpoints (task listing, administrative operations)
- Any endpoint not explicitly exempted above

**Rationale:** Metadata discovery must work for OAuth/MCP compliance without origin restrictions.
Security-sensitive operations (tool execution, API access) require origin validation to mitigate
DNS rebinding and CSRF-like attacks. Health checks are read-only and commonly accessed by monitoring
tools from various origins.

**Implementation:** Middleware applies origin validation based on request method and path pattern matching.

## Consequences

### Positive
- Safer default posture for local HTTP daemon usage.
- Clear operator guidance for when/why to relax defaults.

### Negative / Costs
- Some local client setups may require explicit configuration (origins/bind address).

## Implementation Notes
### Origin validation implementation
- Add `GSD_HTTP_ALLOWED_ORIGINS` environment variable (comma-separated list)
  - Default value: `http://localhost,http://127.0.0.1,http://[::1]` (all ports)
  - Parse and validate on server startup
- Add `GSD_HTTP_ALLOW_NULL_ORIGIN` boolean flag (default: false)
- Implement origin validation middleware with endpoint classification logic:
  - Define exempt patterns: `GET /.well-known/*`, `GET /health`, `OPTIONS *`
  - Apply validation to all other endpoints (POST/PUT/DELETE and `/api/*`)
- Rejection response: `403 Forbidden` with structured error including origin value
- Document DNS rebinding risks in `docs/SECURITY.md`

### Testing and verification
- Requests with unexpected `Origin` are rejected for validated endpoints (403)
- Requests to exempt endpoints work without Origin header
- Null origin allowed only when `GSD_HTTP_ALLOW_NULL_ORIGIN=true`
- Default allowlist includes localhost variants
- Custom allowlist via `GSD_HTTP_ALLOWED_ORIGINS` works correctly
- Bind defaults to loopback
- Sensitive headers are redacted from logs
- Add middleware tests for each endpoint class (exempt vs validated)
- Test origin validation with various origin values (localhost, null, external domains)

### Documentation
- Document the threat model in operator docs (DNS rebinding, cross-origin localhost access)
- Document security tradeoffs of `GSD_HTTP_ALLOW_NULL_ORIGIN` flag
- Add configuration examples for common development scenarios
- Document endpoint classification policy in HTTP API specification

## Resolved Questions

### Origin Validation Policy
**Decision (2026-01-23):** Configurable origin allowlist with null support.

**Implementation:**
- Default allowlist: `http://localhost`, `http://127.0.0.1`, `http://[::1]` (all ports)
- Configurable via `GSD_HTTP_ALLOWED_ORIGINS` environment variable
- Null origin support via `GSD_HTTP_ALLOW_NULL_ORIGIN=true` flag (default: false)
- Reject requests with missing or disallowed origins (403 Forbidden)

**Rationale:** Local development requires flexibility for tools like Postman, browser extensions, and
file:// access. Default to strict localhost, but allow opt-in for null and additional origins via
explicit configuration with documented security warnings. Balances security hardening with developer
convenience.

### Origin Validation Scope
**Decision (2026-01-23):** Validate tool execution only (not all endpoints).

**Implementation:**
- Exempt endpoints: `GET /.well-known/*`, `GET /health`, `OPTIONS *`
- Validated endpoints: POST/PUT/DELETE requests and all `/api/*` endpoints
- Middleware applies validation based on method and path pattern matching

**Rationale:** Metadata discovery must work for OAuth/MCP compliance. Validate POST/PUT/DELETE requests
and all `/api/*` endpoints. Allow GET for `/.well-known/*` and `/health` without origin checks. This
supports standard OAuth discovery patterns while protecting security-sensitive operations.

## References
- `docs/planning/BACKLOG.md`
- MCP security guidance for local HTTP servers
