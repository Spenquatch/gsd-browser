# ADR-0014: Local HTTP security hardening model

## Status
Proposed

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
For endpoints that can be reached from a browser context:
- enforce an allowlist origin policy for local deployments,
- reject unexpected/missing origins where appropriate to mitigate DNS rebinding/CSRF-ish risks.

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

## Consequences

### Positive
- Safer default posture for local HTTP daemon usage.
- Clear operator guidance for when/why to relax defaults.

### Negative / Costs
- Some local client setups may require explicit configuration (origins/bind address).

## Implementation Notes
- Add verification steps/tests:
  - requests with unexpected `Origin` are rejected (local-hardening mode)
  - bind defaults to loopback
  - sensitive headers are redacted from logs
- Document the threat model in operator docs (DNS rebinding, cross-origin localhost access).

## Open Questions
- Exact origin policy (which origins are allowed by default; whether to allow `null` origin).
- Whether origin validation applies to all endpoints or only a subset (e.g., tool calls vs metadata).

## References
- `docs/planning/BACKLOG.md`
- MCP security guidance for local HTTP servers
