# ADR-0020: Remote MCP client configuration and token delivery

## Status
Accepted

## Context
To use `gsd` as a remote MCP server, a user must configure their MCP client with:
- the remote MCP server URL, and
- a way to attach credentials (typically `Authorization: Bearer <token>`).

Different MCP clients have different configuration formats and different capabilities (some can run
OAuth; some can only attach static headers).

We must define a consistent “shape” for token delivery and user onboarding guidance.

## Decision

### 1) The portable contract: URL + Authorization header
The portable configuration contract for remote usage is:
- URL: `https://<host>/<base_path>/mcp`
- Header: `Authorization: Bearer <token>`

This is the only credential delivery mechanism that is both broadly supported and aligned with MCP
HTTP auth guidance.

### 2) Prefer environment variables for secrets
Documentation and generated config snippets SHOULD prefer retrieving the Bearer token from an
environment variable rather than hardcoding secrets into config files.

Rationale:
- prevents accidental token commits,
- supports per-environment injection (CI, dev shells),
- matches common client patterns (e.g., “headers map where values can reference env”).

### 3) `gsd` provides config snippet generation
`gsd` will provide a stable UX to print per-client configuration snippets, including:
- remote URL selection,
- a recommended environment variable name for the token,
- any required transport toggles for the client.

This is an onboarding helper; it must not change the underlying auth contract.

## Consequences

### Positive
- “URL + Bearer token” is easy to explain and consistent across clients.
- Environment variable usage reduces secret leakage risk.
- A single `gsd` command can generate correct client snippets, reducing support load.

### Negative / Costs
- Requires maintaining per-client docs/snippet templates as clients evolve.
- Some clients may not support env var interpolation; docs must provide fallbacks.

## Implementation Notes
- `gsd-browser/docs/api/FAST_MCP_V2_CANONICAL_SPEC.md` remains the source of truth for HTTP auth
  enforcement and base-path behavior (including reverse-proxy hosting).
- Direct (non-MCP) HTTP usage of the 8081 REST API is documented in `gsd-browser/docs/api/HTTP_API.md`
  and uses the same Bearer token delivery model (recommended env var: `GSD_TOKEN`).
- The repo should maintain a small tested set of “known client formats” (Cursor, Windsurf, VS Code,
  Claude Code, Codex, JetBrains, etc.) and treat others as best-effort.

## Resolved Questions

### Token environment variable name
**Decision (2026-01-25):** Use `GSD_TOKEN` as the single blessed environment variable name for the
end-user Bearer token.

Rationale:
- short and easy to document,
- client-agnostic (“headers map can reference env var”),
- avoids implying any specific token type (JWT vs PAT) at the client boundary.

### Tier 1 clients for snippet generation + docs
**Decision (2026-01-25):** Treat the following as “tier 1” for maintained docs/snippets:
- Cursor
- Windsurf
- VS Code
- Claude Code
- Codex CLI
- JetBrains (header-only UX; no browser OAuth assumption)

Other clients are supported best-effort via the portable “URL + Authorization header” contract.

### Documentation order when OAuth is supported
**Decision (2026-01-25):** Document “paste/copy token from portal” first, with “client performs OAuth
directly” as an optional follow-on path.

## Open Questions
None (client config defaults pinned).

## References
- `docs/adr/ADR-0019-remote-auth-token-acquisition-and-login-ux.md`
- `docs/adr/ADR-0013-mcp-compliant-http-authorization-surfaces-and-scope-model.md`
- `gsd-browser/docs/api/FAST_MCP_V2_CANONICAL_SPEC.md`
