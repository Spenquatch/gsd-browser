# ADR-0013: MCP-compliant HTTP authorization surfaces and scope model

## Status
Accepted

## Context
`gsd` supports an HTTP transport for MCP (Streamable HTTP). For multi-tenant server deployments, HTTP
authorization behavior is part of the external contract:
- how clients discover authorization requirements,
- how servers challenge unauthenticated requests,
- how servers indicate “insufficient scope” and guide step-up,
- how tokens are validated for the correct resource/audience.

Today, `gsd`’s HTTP mode is primarily “JWT verification” (issuer/JWKS/audience checks). To become
fully MCP-compliant for HTTP authorization surfaces, we need to add the discovery and challenge
semantics expected by the MCP spec and referenced OAuth RFCs.

## Decision

### 1) Implement OAuth 2.0 Protected Resource Metadata discovery (RFC 9728)
Expose Protected Resource Metadata under `/.well-known/` for the MCP HTTP service with path-aware
support for reverse proxy and subpath hosting scenarios.

**Path-aware metadata endpoints:**
- Serve metadata at `/.well-known/oauth-protected-resource` for root hosting
- Serve metadata at `{base_path}/.well-known/oauth-protected-resource` when hosted under a subpath
- Detect base path via:
  1. `GSD_HTTP_BASE_PATH` configuration variable (explicit override)
  2. `X-Forwarded-Prefix` header (reverse proxy detection)
  3. Default to `/` (root) if neither is present

**Rationale:** Real-world deployments use reverse proxies and subpaths (Kubernetes ingress, shared
hosting). Path awareness is required for production flexibility and follows MCP HTTP spec guidance.

**Configuration:**
- `GSD_HTTP_BASE_PATH`: Optional base path for metadata URLs (e.g., `/mcp/gsd`)
- All metadata URLs in responses are path-relative to detected base path

### 2) Standardize `WWW-Authenticate` challenge semantics
For HTTP requests that require auth:
- `401 Unauthorized`: include `WWW-Authenticate: Bearer ...` and include a `resource_metadata=...`
  parameter pointing at the RFC 9728 metadata endpoint.
- `403 Forbidden`: when authenticated but missing required scope, include
  `WWW-Authenticate: Bearer error="insufficient_scope", scope="..."` to support least-privilege
  progression.

### 3) Define a scope model for MCP operations
Use a capability-based scope model with three tiers:

**Scope definitions:**
- `gsd:browser:execute` - Execute browser automation tools
  - Grants access to: `web_eval_agent`, `setup_browser_state`
  - Required for: job submission tools (`web_eval_agent_submit`, etc.)
- `gsd:browser:read` - Read browser execution artifacts and telemetry
  - Grants access to: `get_screenshots`, `get_run_events`
  - Required for: job status/result tools (`job_get`, `job_result`)
- `gsd:admin` - Full administrative access
  - Grants access to: all operations including cross-tenant operations and system management

**Scope to tool mapping:**
- Execution tools require `gsd:browser:execute` or `gsd:admin`
- Read-only artifact tools require `gsd:browser:read` or `gsd:admin`
- Administrative endpoints require `gsd:admin` only

**Discovery:**
- Clients discover required scopes via:
  1. Protected Resource Metadata (`/.well-known/oauth-protected-resource`)
  2. `WWW-Authenticate` challenges with `scope="..."` parameter
  3. `403 Forbidden` responses with `insufficient_scope` error and required scope listing

**Rationale:** Three-tier capability model balances simplicity and security. Simpler than per-tool
scopes while providing natural groupings (execute vs read). Existing tool policy (allowlist/denylist
from ADR-0006) provides additional fine-grained enforcement within scope boundaries.

### 4) Enforce resource/audience binding (RFC 8707 Resource Indicators)
Tokens must be minted for this protected resource:
- enforce `aud`/resource binding (or equivalent) so we do not accept tokens intended for other
  services,
- do not forward/pass through bearer tokens to downstream systems.

**Wrong audience error policy:**
Return `403 Forbidden` with audience hint for better operator observability.

**Error response format:**
```json
{
  "error": "invalid_token",
  "error_description": "Token audience does not match protected resource",
  "expected_audience": "https://gsd.example.com",
  "actual_audience": "https://other-service.example.com"
}
```

**Headers:**
- Include `WWW-Authenticate: Bearer error="invalid_token"` in response
- Log all audience validation failures for security monitoring

**Rationale:** Knowing a resource exists is low-value information for attackers. Clear error feedback
dramatically improves operator experience and reduces misconfigurations. Including expected and actual
audience values in error detail enables rapid troubleshooting.

### 5) Transitional “JWT verification only” mode is allowed but must be explicit
Allow a transitional mode where only JWT verification is enforced (no RFC 9728 metadata and/or
reduced challenge semantics), but:
- it must be explicitly configured (feature flag / env),
- behavior differences must be documented for operators and clients,
- conformance tests must run with the “compliant” mode enabled.

## Consequences

### Positive
- Aligns HTTP transport with MCP spec guidance and OAuth RFC requirements.
- Enables better client UX (discoverable requirements; actionable step-up prompts).
- Reduces security foot-guns by enforcing resource/audience binding.

### Negative / Costs
- More endpoints and semantics to implement and test.
- Requires careful compatibility handling for existing deployments that rely on JWT-only behavior.

## Implementation Notes
### Path-aware metadata implementation
- Add `GSD_HTTP_BASE_PATH` configuration variable
- Implement `X-Forwarded-Prefix` header detection in HTTP middleware
- Serve metadata at both `/.well-known/oauth-protected-resource` and `{base_path}/.well-known/oauth-protected-resource`
- Update all metadata URLs to be path-relative (authorization_endpoint, token_endpoint, etc.)
- Add configuration validation tests for various base path scenarios

### Scope validation implementation
- Define three initial scopes in configuration: `gsd:browser:execute`, `gsd:browser:read`, `gsd:admin`
- Map each tool/endpoint to required scope(s)
- Update `WWW-Authenticate` challenge to include `scope="..."` parameter with required scopes
- Add scope validation middleware to HTTP request pipeline
- For `403 insufficient_scope` responses, include list of required scopes for the requested operation

### Scope claim extraction (pinned)
Scope extraction from JWT claims is pinned as follows:
- Prefer claim `scope` (string; space-separated), fallback to `scp`.
- `scp` may be either:
  - an array of strings, or
  - a space-separated string.
- Any invalid scope claim format results in “no scopes” (treated as insufficient scope).

### Audience validation implementation
- Return `403 Forbidden` for wrong audience with structured error response
- Include `expected_audience` and `actual_audience` (from token claims) in error response body
- Add `WWW-Authenticate: Bearer error="invalid_token"` header to response
- Log all audience validation failures to security audit log with:
  - timestamp, client IP, expected audience, actual audience, requested endpoint
- Document error format in HTTP API specification

### Authorization test matrix
- Add a test matrix for:
  - no token -> `401` with `resource_metadata=...`
  - token valid but missing scope -> `403` with `insufficient_scope` + scope listing
  - wrong audience/resource -> `403` with audience hint (expected vs actual)
  - token valid + sufficient scope -> success
- Ensure metadata is correct when hosted under a base path (reverse proxies)
- Test base path detection from both config and header sources
- Test scope enforcement for each scope tier (execute, read, admin)
- Test audience validation with various mismatched audience values

## Resolved Questions

### Protected Resource Metadata Endpoint Paths
**Decision (2026-01-23):** Path-aware metadata with base path detection.

**Implementation:** Serve metadata at both `/.well-known/oauth-protected-resource` (root) and
`{base_path}/.well-known/oauth-protected-resource` (subpath). Detect base path via `GSD_HTTP_BASE_PATH`
configuration variable or `X-Forwarded-Prefix` header.

**Rationale:** Real-world deployments use reverse proxies and subpaths. Path awareness is required for
production flexibility and aligns with MCP HTTP spec guidance.

### OAuth Scope Granularity
**Decision (2026-01-23):** Capability-based scopes with three tiers.

**Implementation:** Define three scopes:
- `gsd:browser:execute` - Execute browser automation tools (web_eval_agent, setup_browser_state)
- `gsd:browser:read` - Read artifacts and telemetry (get_screenshots, get_run_events)
- `gsd:admin` - Full administrative access (all operations)

**Rationale:** Three-tier capability model balances simplicity and security. Simpler scope management than
per-tool scopes while providing natural groupings (execute vs read). Existing tool policy (ADR-0006
allowlist/denylist) provides additional fine-grained enforcement within scope boundaries.

### Wrong Audience Error Policy
**Decision (2026-01-23):** Return `403 Forbidden` with audience hint.

**Implementation:** Return `403 Forbidden` with structured error response including `expected_audience` and
`actual_audience` (from token claims). Log all audience validation failures for security monitoring.

**Rationale:** Knowing a resource exists is low-value information for attackers. Clear error feedback
dramatically improves operator experience and reduces misconfigurations. Audience hints enable rapid
troubleshooting without security risk.

## Open Questions
### Protected Resource Metadata: multiple “resources”
**Decision (2026-01-24):** Single protected resource per server deployment.

The server supports path-aware hosting under a base path (serving
`{base_path}/.well-known/oauth-protected-resource`), but it does not attempt to present multiple
distinct protected resources from a single running instance (no host-based multi-resource behavior).

## References
- `docs/planning/BACKLOG.md`
- OAuth 2.0 Protected Resource Metadata (RFC 9728)
- OAuth 2.0 Resource Indicators (RFC 8707)
