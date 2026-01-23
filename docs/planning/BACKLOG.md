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
- **DONE**: ADR-0013 is now **Accepted** and defines:
  - path-aware Protected Resource Metadata (base path detection via `GSD_HTTP_BASE_PATH` and `X-Forwarded-Prefix`)
  - a three-tier capability scope model (`gsd:browser:execute`, `gsd:browser:read`, `gsd:admin`)
  - wrong-audience policy (`403` with `WWW-Authenticate: Bearer error="invalid_token"` and audience hints)

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

### Task lookup must not depend on the current MCP session (DONE)
FastMCP’s built-in task protocol handlers key task metadata by `session_id` in Redis. For “check later”
workflows (and compat job tools), we must not require that the MCP host reuses the same `mcp-session-id`.


**DONE**: Implemented session-independent `tasks/get|result|cancel` by using the persisted TaskOwnershipRecord (including the originating `session_id`) to locate the underlying Docket task across new sessions/restarts. See `gsd-browser/src/gsd_browser/optionb/fastmcp_server.py` and ADR-0012.

- If `tasks/get|result|cancel` effectively require the *current* `mcp-session-id` to match the originating
  one, then “check later” breaks even when identity matches.
- If we intend “check later” to work for SEP-1686 tasks as well (not just compat jobs), we need an explicit
  mapping/lookup strategy that is independent of the current session ID.

- Implement session-independent lookup for status/result/cancel using persisted ownership records.
  - Task ownership already persists `session_id`; use it for lookups rather than the *current* session.
  - Consider persisting the full Docket task key (or a mapping) if required for robust lookup.
- Add conformance tests:
  - create task in session A, then fetch status/result in session B (same identity) succeeds
  - cross-tenant denial remains non-enumerable
Track contract decisions in ADR-0012.

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

Notes:
- Prefer HTTP daemon mode for Codex/client-independent execution in practice; prefer stdio for local/dev
  convenience.

### Compat job tools: progress + session IDs
Compat job tools should support “progress while running” without relying on SEP-1686 notifications.

- Align the compat jobs external contract (tool names, job IDs, and state model) with ADR-0011:
  - `{tool_name}_submit(...)` returns an opaque, stable `job_id` (not a raw backend task key).
  - `job_get(job_id)` returns a stable state vocabulary (`queued|running|completed|failed|cancelled`) and a
    best-effort `progress_message` snapshot (plus timestamps).
  - `job_result(job_id)` returns the final tool payload schema (same as the tool payload / `tasks/result`)
    once terminal.
  - `job_cancel(job_id)` cancels the job (non-enumerable “not found” on unauthorized).
- Define minimal progress surface:
  - Docket progress message snapshot (always available)
  - optional: run-events / screenshots availability during execution
- Decide how/when `session_id` becomes known for compat jobs:
  - pre-allocate browser `session_id` at submit-time (recommended for “check while running”), or
  - emit it once known via progress/status updates
**DONE**: ADR-0011 is now **Accepted** (compat jobs contract, including `job_wait` and progress fields).

### HTTP local security hardening (spec guidance)
For local HTTP deployments, add the missing hardening expected by MCP security guidance.

- Validate `Origin` on HTTP requests (DNS rebinding mitigation).
- Bind to localhost by default for local deployments.
- Ensure logs never include secrets/tokens and redact sensitive headers.
Track contract decisions in ADR-0014.

### Job retention + cleanup policy (separate from task TTL)
Once we add compat jobs, we will likely have two clocks:
- task TTL / backend retention (Docket/task store), and
- business-level “job retention” (how long after completion we support `job_result` and artifact fetches).

Decide this explicitly to avoid:
- jobs disappearing “too soon” for Codex workflows, or
- unbounded retention (storage growth).
ADR-0017 is now **Accepted** and defines default retention windows + cleanup observability requirements:
- Dev defaults: jobs 24h, artifacts 12h
- Prod defaults: jobs 7d, artifacts 3d
- Cleanup emits Prometheus metrics and structured logs

### Maintenance leadership (where pruning runs)
If artifact cleanup / pruning is coordinated via a distributed lock (e.g., Redis), decide which process is
responsible for running maintenance in "server concurrency=0, external workers=N":
- MCP server process,
- worker processes, or
- a dedicated "maintenance" process.

This choice affects deployment docs and reliability.
**DONE**: ADR-0015 is now **Accepted** and chooses **worker-led maintenance**.

### Artifact cleanup entrypoint (blocked on worker/maintenance wiring)
`CleanupRunner` is implemented and tested (`optionb/artifact_index.py`), but nothing schedules it.
Without a deployed cleanup process, S3 objects accumulate even after Redis metadata expires.

**Action items**:
1. Wire a maintenance loop into the worker process per ADR-0015 (worker-led leader election + scheduled run).
2. Standardize the interval env var name and docs:
   - ADR-0015 uses `GSD_MAINTENANCE_INTERVAL` (default: 300s).
3. Ensure the maintenance loop enforces the retention policy from ADR-0017 (dev/prod defaults).
4. Add an integration test that verifies cleanup runs in a real deployment scenario.

**Current workaround**: Operators can invoke `CleanupRunner.run_once()` manually via a custom script or
external scheduler (cron, k8s CronJob) until a first-class entrypoint is provided.

### Task/job enumeration surfaces (ADR-0018 Accepted)
Task enumeration is **not** part of the supported MCP protocol surface for Option B:
- `tasks/list` stays disabled (METHOD_NOT_FOUND) per ADR-0012 / ADR-0018.

Instead, enumeration/inspection is an operations surface:
- **8081** management/admin REST API (task/job listing + inspection), documented in
  `gsd-browser/docs/api/HTTP_API.md`.
- CLI surfaces (e.g., `gsd tasks list`) built on the 8081 API.

Additionally, if we want synchronous MCP clients (or stdio-only deployments) to have an
enumeration/inspection workflow, we can expose **MCP tools** that proxy the same underlying
implementation as the 8081 API (this is *not* the MCP protocol `tasks/list` method). Example shape:
- `tasks_list(...)` / `jobs_get(...)` tools that call into the same identity-scoped listing/get logic.

**Action items**:
- Implement the 8081 management REST API endpoints (`GET /api/v1/tasks`, `GET /api/v1/jobs/{job_id}`)
  with identity-scoped filtering and safe-by-default admin gating.
- Reuse the same identity extraction rules as 8080 (MCP HTTP) and preserve non-enumerability semantics
  (unauthorized vs nonexistent vs expired should not be distinguishable for non-admin callers).
- Apply local HTTP hardening guidance when browser-reachable (ADR-0014).
- Decide whether to add MCP tool wrappers for listing/inspection (and their naming/scope), and ensure
  they do not re-introduce cross-identity enumerability.

### Spec + runtime alignment
Reduce operator confusion and prevent drift between docs and what actually runs.

- ~~Reconcile `GSD_REDIS_URL` usage~~ **DONE**: Removed from canonical spec; all Redis usage goes
  through `FASTMCP_DOCKET_URL`. See ADR-0016 (Accepted).
- Update status docs so they match reality (implemented vs planned boundary).
