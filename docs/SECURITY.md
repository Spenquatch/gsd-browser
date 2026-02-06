# Security notes (operator + developer)

This document captures security considerations for running `gsd` locally and in multi-tenant server
deployments. It is not a complete threat model, but it documents the specific risks that drive the
hardening decisions recorded in ADRs.

## Local HTTP threat model (why localhost is not automatically safe)

Running an HTTP service on loopback (e.g., `127.0.0.1`) still exposes you to browser-mediated attacks,
including:

- **DNS rebinding**: a malicious web page can cause a browser to resolve a domain to loopback and then
  issue requests to localhost services, potentially bypassing naive “localhost only” assumptions.
- **Cross-origin localhost requests**: browsers can send requests to localhost from an untrusted origin.
  If your service accepts state-changing requests without additional checks, it can be abused in a
  CSRF-like way.

These issues do not apply in the same way to stdio subprocess transports, which is why local HTTP
deployments require explicit hardening.

## Defensive defaults

For local HTTP deployments, `gsd` should:

- Bind to loopback by default.
- Validate `Host` (and forwarded host headers when relevant) against a strict allowlist.
- Validate `Origin` for security-sensitive endpoints (tool execution and management APIs).
- Redact sensitive headers (e.g., `Authorization`) from logs and structured events.
- Treat CORS as opt-in (avoid permissive defaults).

See `docs/adr/ADR-0014-local-http-security-hardening-model.md` for the canonical decisions.

## Why prod scripts send `Origin`

Production management endpoints enforce an `Origin` allowlist as a defense-in-depth control against
browser-mediated requests (CSRF-style cross-origin calls). The `gsd-browser/scripts/prod_*.sh`
scripts always include an explicit `Origin` header (override via `GSD_ORIGIN`) so operator tooling
matches the dashboard origin policy and avoids `origin_not_allowed` failures.
