# ADR-0013: MCP-compliant HTTP authorization surfaces and scope model

## Status
Proposed

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
Expose Protected Resource Metadata under `/.well-known/` for the MCP HTTP service, including
path-aware variants when the MCP server is hosted under a subpath.

### 2) Standardize `WWW-Authenticate` challenge semantics
For HTTP requests that require auth:
- `401 Unauthorized`: include `WWW-Authenticate: Bearer ...` and include a `resource_metadata=...`
  parameter pointing at the RFC 9728 metadata endpoint.
- `403 Forbidden`: when authenticated but missing required scope, include
  `WWW-Authenticate: Bearer error="insufficient_scope", scope="..."` to support least-privilege
  progression.

### 3) Define a scope model for MCP operations
Define and document:
- scope strings the server emits (and enforces) for MCP operations,
- how scope requirements map to tool/method access,
- how clients can discover required scopes (via metadata and/or error responses).

### 4) Enforce resource/audience binding (RFC 8707 Resource Indicators)
Tokens must be minted for this protected resource:
- enforce `aud`/resource binding (or equivalent) so we do not accept tokens intended for other
  services,
- do not forward/pass through bearer tokens to downstream systems.

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
- Add a test matrix for:
  - no token -> `401` with `resource_metadata=...`
  - token valid but missing scope -> `403` with `insufficient_scope` + scope listing
  - wrong audience/resource -> `401`/`403` (explicit policy)
  - token valid + sufficient scope -> success
- Ensure metadata is correct when hosted under a base path (reverse proxies).

## Open Questions
- Exact endpoint paths and whether the server supports multiple “resources” (path-aware metadata).
- Exact scope strings and how granular they should be (per-tool vs per-capability).
- Exact error policy for “wrong audience” (401 vs 403) and operator observability needs.

## References
- `docs/planning/BACKLOG.md`
- OAuth 2.0 Protected Resource Metadata (RFC 9728)
- OAuth 2.0 Resource Indicators (RFC 8707)

