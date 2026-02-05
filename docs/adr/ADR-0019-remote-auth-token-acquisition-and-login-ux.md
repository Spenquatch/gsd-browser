# ADR-0019: Remote auth, token acquisition, and login UX

## Status
Accepted

## Context
`gsd` is evolving into a primarily **remote** (cloud) MCP server that users add to their MCP client
configuration.

We already have an MCP-over-HTTP transport (Streamable HTTP) with:
- `Authorization: Bearer <token>` support,
- OAuth Protected Resource Metadata discovery (`/.well-known/oauth-protected-resource`),
- `WWW-Authenticate` challenge semantics,
- scope enforcement.

However, “HTTP auth enforcement” alone is not enough for end-user adoption: we must define how a user
obtains a token (sign-in UX), and how that token is supplied to different MCP clients.

Constraints:
- MCP HTTP transports can carry credentials via HTTP headers; stdio cannot.
- Many clients support direct remote MCP-over-HTTP; some remain stdio-only.
- We want to remain IdP/provider-agnostic (Clerk is likely, but not required).

## Decision

### 1) Primary path: remote MCP-over-HTTP + Bearer tokens
The primary integration path for end users is:
- MCP client connects directly to `https://<host>/<base_path>/mcp` (Streamable HTTP MCP).
- MCP client attaches `Authorization: Bearer <token>` on every request.

HTTP auth semantics are governed by:
- ADR-0013 (OAuth discovery + challenges + scope model)
- ADR-0014 (local HTTP hardening)
- `gsd-browser/docs/api/FAST_MCP_V2_CANONICAL_SPEC.md` (authoritative/pinned contract)

### 2) Token format and validation (pinned at the `gsd` server boundary)
For HTTP transport, `gsd` remains a **resource server**. It does not “own” user login UI or act as an
OAuth authorization server.

Pinned server expectations for HTTP mode:
- Access tokens are presented as `Authorization: Bearer <token>`.
- Tokens MUST be verifiable via configured JWT parameters (`issuer`, `audience`, `jwks_url`), and
  MUST include the tenant/subject claim mapping required by the canonical spec.

Rationale:
- This keeps the MCP server boundary clean and aligns with MCP’s HTTP auth guidance.
- It allows operators to choose an IdP (including Clerk) without changing `gsd` core semantics.

### 3) End-user “sign in” UX is delivered via a companion auth surface (outside MCP)
We will provide a user-facing sign-in UX that results in a token suitable for MCP clients.

Minimum required UX surfaces:
- A web sign-in flow (IdP hosted or first-party UI) that can mint/copy an access token suitable for
  MCP client configuration.
- A CLI-assisted sign-in path (`gsd auth login`) for terminal-first onboarding.

Notes:
- The exact OAuth flow used by the CLI (device code vs browser-based auth code + PKCE) is an
  implementation choice; the pinned outcome is “user can obtain a Bearer token that works with
  remote MCP-over-HTTP”.

### 4) Scope assignment is authoritative; issuance can vary
Scope semantics remain pinned by ADR-0013 and the canonical spec.

Token issuance (IdP templates/claims, or a companion issuance service) MUST ensure the token’s scope
claims match the pinned extraction rules and intended permissions.

## Consequences

### Positive
- Remote HTTP becomes the mainline product path: “configure URL + Bearer token”.
- Auth remains standards-aligned (Bearer tokens, discovery/challenges) and provider-agnostic.
- Login UX can iterate independently without destabilizing MCP behavior.

### Negative / Costs
- Requires building and operating additional auth UX (portal and/or CLI login flows).
- Different MCP clients have different configuration formats; onboarding must be explicit.

## Implementation Notes
- Canonical/pinned auth behavior is documented in `gsd-browser/docs/api/FAST_MCP_V2_CANONICAL_SPEC.md`
  and is the source of truth.
- Clerk compatibility notes (JWT templates / claim shaping) are documented in the canonical spec and
  should be kept current as Clerk evolves.

## Resolved Questions

### Initial IdP/provider for hosted sign-in UX
**Decision (2026-01-25):** Standardize on **Clerk** for the initial hosted sign-in UX.

### Default onboarding path for token acquisition
**Decision (2026-01-25):** Document a “copy token from portal” onboarding flow first.

Rationale:
- Works across the widest set of MCP clients that support remote HTTP + headers, regardless of
  whether they support an embedded browser OAuth UX.
- Minimizes initial surface area while we validate tenancy, scope assignment, and end-to-end auth
  enforcement.

Follow-on:
- Add “OAuth-capable clients perform OAuth directly” as an optional/enhanced path after the portal
  flow is shipped and stable.

### Token lifetime policy (short-lived vs long-lived)
**Decision (2026-01-25):** Support both, with strict guidance:
- Default: short-lived access tokens (preferred when a client can do OAuth / PKCE / device-code).
- Also support long-lived “developer tokens” (PAT-style) as a compatibility fallback for clients
  with limited OAuth UX or static header config.

For direct (non-MCP) automation against the 8081 REST API, API keys (`X-API-Key`) are also supported
as a first-class mechanism (see `gsd-browser/docs/api/HTTP_API.md`).

Constraints for long-lived developer tokens (pinned expectations):
- Must be explicitly created/managed in the portal (show-once), revocable, and audited (created_at,
  last_used_at, label).
- Must be scope-limited (least privilege); treat `gsd:admin` developer tokens as exceptional.
- Operators should prefer server-side storage as hashes (e.g., SHA-256) rather than plaintext.

## Open Questions
None (auth productization defaults pinned).

## References
- `docs/adr/ADR-0013-mcp-compliant-http-authorization-surfaces-and-scope-model.md`
- `docs/adr/ADR-0014-local-http-security-hardening-model.md`
- `gsd-browser/docs/api/FAST_MCP_V2_CANONICAL_SPEC.md`
- `gsd-browser/docs/api/STATUS.md`
