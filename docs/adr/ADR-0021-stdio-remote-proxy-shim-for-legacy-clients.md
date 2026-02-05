# ADR-0021: stdio→remote-HTTP proxy shim for legacy MCP clients (deferred)

## Status
Accepted

## Context
The primary product path is remote MCP-over-HTTP, where a client connects directly to the cloud
server and sends `Authorization: Bearer <token>`.

However, some MCP clients remain **stdio-only** or have partial remote-HTTP support. Those clients
cannot directly:
- connect to a remote MCP-over-HTTP server,
- attach custom headers, and/or
- participate in OAuth discovery/challenge flows.

We want to support these clients eventually, but without blocking the mainline “remote HTTP”
productization work.

## Decision

### 1) Implement a local stdio proxy shim, but defer it (backlog)
We will implement a local `gsd` “proxy” mode that:
- speaks MCP stdio to the host client,
- forwards MCP calls to the remote `https://.../mcp` endpoint using Streamable HTTP,
- attaches `Authorization: Bearer <token>` to the remote hop.

This work is explicitly **deferred** until after the mainline remote-HTTP auth + onboarding work is
complete.

### 2) The shim is a compatibility layer, not the default path
The shim is intended only for:
- stdio-only clients, and
- edge cases where a client cannot express headers or remote auth requirements.

For any client that can connect directly via Streamable HTTP with headers, direct remote config is
preferred.

## Consequences

### Positive
- Preserves compatibility with stdio-only MCP clients without compromising the remote HTTP design.
- Allows `gsd` to implement richer local auth UX (token caching/refresh) independently of the MCP
  host.

### Negative / Costs
- Adds an extra moving piece on the user’s machine (a local background shim process).
- Requires careful error UX (“not logged in”, expired token) without breaking stdio JSON-RPC.

## Implementation Notes
- The shim must treat stdout as MCP JSON-RPC only (no noise); user-facing guidance goes to stderr.
- The shim should reuse the same contract models and tool mappings as the direct remote server.
- The shim must not weaken security: it is not an auth bypass; it only transports credentials the
  user already obtained.

## Resolved Questions

### CLI UX shape
**Decision (2026-01-25):** Use `gsd mcp serve --remote <https_url>` as the primary UX shape.

Rationale:
- Remote HTTPS is the primary product path; the shim is a deferred compatibility layer.
- “Proxy” framing is an implementation detail; `--remote` communicates intent and future-proofing.

### Token refresh behavior in the shim
**Decision (2026-01-25):** Defer refresh-token support in shim v1.

Shim v1 assumes a long-lived token (PAT-style / developer token) supplied via `GSD_TOKEN`.

Rationale:
- Clerk SDK patterns for refresh are strongly web/session-cookie oriented; we do not rely on a
  headless refresh-token flow for the initial shim.
- Keeps the shim simple and avoids embedding OAuth complexity in a deferred feature.
- Short-lived tokens (e.g., very short TTL session-style tokens) are not a realistic shim input for
  long-running automation and are not supported in shim v1.

### “Auto-login” behavior on `401` challenges
**Decision (2026-01-25):** Defer auto-login in shim v1; prefer clear, non-blocking guidance.

Shim v1 behavior on `401` from the remote server:
- Return a deterministic MCP error indicating “not authenticated”.
- Print actionable instructions to **stderr** only (never stdout), e.g.:
  - “Run `gsd auth login`” (future), or
  - “Create/copy a token from the portal and set `GSD_TOKEN`”.

Follow-on (optional):
- Add an opt-in `--auto-login` / `GSD_SHIM_AUTO_LOGIN=1` that performs a device-code style flow and
  polls for completion, without breaking stdio JSON-RPC semantics.

## Open Questions
None (shim v1 decisions pinned; implementation deferred/backlog).

## References
- `docs/adr/ADR-0019-remote-auth-token-acquisition-and-login-ux.md`
- `docs/adr/ADR-0020-remote-mcp-client-configuration-and-token-delivery.md`
- `docs/adr/ADR-0007-cli-contract-and-gsd-binary.md`
- `docs/adr/ADR-0013-mcp-compliant-http-authorization-surfaces-and-scope-model.md`
