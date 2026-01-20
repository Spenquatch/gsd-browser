# Backlog: FastMCP v2 Option B follow-ons

This backlog captures remaining work after the initial FastMCP v2 Option B landing, with a focus on:
1) full MCP-compliant HTTP authorization surfaces, and
2) decoupling long-running execution from the MCP host lifecycle (Codex-compatible).

## Implication for `gsd` (HTTP auth compliance)

### OAuth discovery + challenge surfaces (MCP spec compliance)
Our current HTTP approach is primarily **token verification** (JWT validation: JWKS/issuer/audience),
which is a good baseline, but “fully MCP compliant” HTTP authorization eventually also includes:

- Implementing OAuth 2.0 Protected Resource Metadata (RFC 9728) discovery:
  - Serve `/.well-known/oauth-protected-resource/...` (path-aware)
  - Emit `WWW-Authenticate` with `resource_metadata=...` on `401 Unauthorized`
- Proper `WWW-Authenticate` semantics for scope step-up:
  - `403` with `error="insufficient_scope"` and `scope="..."` for least-privilege progression
- Enforcing resource/audience binding (RFC 8707 Resource Indicators):
  - Ensure tokens are minted for this resource (`aud` / equivalent)
  - No token passthrough (do not accept/forward tokens intended for other resources)

Notes:
- These are primarily relevant for HTTP transport and multi-tenant deployments.
- `stdio` remains a local trust boundary (`tenant_id=local`, `subject_id=local`).

## Implication for `gsd` (detached execution + multi-tenant correctness)

### Identity propagation into detached workers
The “identity propagation into detached workers” requirement becomes critical once we decouple task
execution from the MCP server process:

- Background execution (Docket workers) does not automatically carry HTTP request auth context.
- If tasks run outside the MCP server process and we rely on JWT-derived identity, we must:
  - explicitly persist/pass identity (`tenant_id`, `subject_id`, transport) into the enqueued work
  - re-establish `identity_scope(...)` inside the worker execution path before writing artifacts or
    making authorization-relevant decisions

Notes:
- For Codex/local/stdio (`tenant_id=local`), this can be deferred.
- For HTTP multi-tenant deployments, this is required to prevent cross-tenant artifact index writes.

## Suggested next work items (tracking)

- Add MCP OAuth surfaces for HTTP transport:
  - Protected Resource Metadata endpoint(s)
  - `WWW-Authenticate` challenges for `401` + `403 insufficient_scope`
  - Resource indicator / audience binding verification and tests
- Add “client-independent” long jobs (Codex compatible):
  - Run execution in external workers (server processes do not execute tasks)
  - Add “compat jobs” tool surface (submit/status/result/cancel/wait)
  - Ensure compat job lookups do not depend on the current MCP session ID
- Add explicit identity propagation for detached workers (HTTP):
  - Persist identity with the job/task record (or pass in task args)
  - Re-enter `identity_scope` in worker execution paths

## Additional gaps to plan for

### Task lookup must not depend on the current MCP session
FastMCP’s built-in task protocol handlers key task metadata by `session_id` in Redis. For “check later”
workflows (and compat job tools), we must not require that the MCP host reuses the same `mcp-session-id`.

- Implement session-independent lookup for status/result/cancel using persisted ownership records.
  - Task ownership already persists `session_id`; use it for lookups rather than the *current* session.
  - Consider persisting the full Docket task key (or a mapping) if required for robust lookup.
- Add conformance tests:
  - create task in session A, then fetch status/result in session B (same identity) succeeds
  - cross-tenant denial remains non-enumerable

### First-class worker entrypoint + deployment docs
We need a canonical way to run external workers for `gsd` (not an ad-hoc command).

- Add a documented and scripted “worker entrypoint” for `gsd` (local + prod patterns).
  - Standardize `FASTMCP_DOCKET_NAME` usage and document defaults.
  - Document and validate the “concurrency split”:
    - server: `FASTMCP_DOCKET_CONCURRENCY=0`
    - workers: `FASTMCP_DOCKET_CONCURRENCY>0`
- Add a “full Option B compose” for local validation:
  - server (http or stdio as needed)
  - valkey (redis backend)
  - worker(s)
  - optional seaweedfs (S3 gateway) for artifact persistence

### First-class HTTP transport runtime (daemon-style)
Codex can connect to Streamable HTTP MCP servers by URL; this is the cleanest way to avoid stdio
subprocess lifecycle coupling.

- Add a first-class command/docs for running the MCP HTTP server (ASGI) as a service.
- Document Codex configuration for Streamable HTTP transport (url/headers/token env vars).
- Ensure HTTP mode includes local-security hardening (below).

### Compat job tools: progress + session IDs
Compat job tools should support “progress while running” without relying on SEP-1686 notifications.

- Define minimal progress surface:
  - Docket progress message snapshot (always available)
  - optional: run-events / screenshots availability during execution
- Decide how/when `session_id` becomes known for compat jobs:
  - pre-allocate browser `session_id` at submit-time (recommended for “check while running”), or
  - emit it once known via progress/status updates

### HTTP local security hardening (spec guidance)
For local HTTP deployments, add the missing hardening expected by MCP security guidance.

- Validate `Origin` on HTTP requests (DNS rebinding mitigation).
- Bind to localhost by default for local deployments.
- Ensure logs never include secrets/tokens and redact sensitive headers.

### Spec + runtime alignment
Reduce operator confusion and prevent drift between docs and what actually runs.

- Reconcile `GSD_REDIS_URL` usage:
  - It is referenced in the canonical spec but is not wired as a runtime configuration input today.
  - Either wire it (as an alias/override) or remove/clarify it in the spec/docs.
- Update status docs so they match reality (implemented vs planned boundary).

