# GSD MCP API Status (canonical)

This file is the single source of truth for what is **implemented today** vs **planned** for the
FastMCP v2 (Option B) runtime.

## Implemented vs planned

### Implemented today (current runtime)
- MCP tools are available via the legacy SDK runtime (`mcp.server.fastmcp`) for stdio.
- A FastMCP v2 stdio entrypoint is implemented behind `GSD_USE_FASTMCP_V2=true`.
- FastMCP v2 requires Redis/Valkey via `FASTMCP_DOCKET_URL` (even on stdio).
- A FastMCP v2 HTTP (ASGI) entrypoint is implemented when `GSD_TRANSPORT=http` and JWT config is present.
  - HTTP transport is configured as stateless (`stateless_http=True`) so clients do not need to reuse `mcp-session-id` headers across calls.
- A supported external worker entrypoint exists for Option B via `gsd worker`:
  - Server process can be run with `FASTMCP_DOCKET_CONCURRENCY=0` (does not execute tasks).
  - Worker process(es) can be run with `FASTMCP_DOCKET_CONCURRENCY>0` (executes queued work).
  - Both must share the same Docket backend (`FASTMCP_DOCKET_URL`, `FASTMCP_DOCKET_NAME`).
  - Example (two-process topology):
    - `GSD_USE_FASTMCP_V2=true FASTMCP_DOCKET_CONCURRENCY=0 gsd serve`
    - `GSD_USE_FASTMCP_V2=true FASTMCP_DOCKET_CONCURRENCY=4 gsd worker`
- Tool responses follow the JSON payload schemas documented in `gsd-browser/docs/api/MCP_TOOLS.md`.
- SEP-1686 long-running tasks are implemented for long tools in the FastMCP v2 runtime:
  - long tools are task-required in v2
  - `tasks/get`, `tasks/result`, `tasks/cancel` handlers are active with ownership enforcement
  - task lookup is session-independent (create in one session, fetch/cancel in another) via persisted
    ownership records (ADR-0012 Accepted)
  - progress notifications are emitted during agent work
- Distributed artifact storage is implemented (S3-compatible object store + Redis index) and is used when
  the required S3 env vars are configured.
- A management/admin REST API (port 8081) is implemented (ADR-0018):
  - `/healthz`
  - `GET /api/v1/tasks` (identity-scoped)
  - `GET /api/v1/admin/tasks` (admin-gated; requires `GSD_ADMIN_MODE=1` + `gsd:admin`)

### Implemented but not deployed
- **Artifact cleanup/retention enforcement**: `CleanupRunner` exists in `optionb/artifact_index.py` and is
  fully tested, but **no process currently schedules it**. S3 objects and Redis index entries will
  accumulate until a maintenance entrypoint is deployed. The canonical spec (§4.3 "Cleanup rules") documents
  this as "required", but worker-led maintenance is not wired/deployed yet (ADR-0015 Accepted).
  - Operators requiring cleanup today must invoke `CleanupRunner.run_once()` manually or via external
    scheduling (cron, k8s CronJob, etc.).
  - See ADR-0015 (operational topology) and ADR-0017 (retention policy) for the accepted defaults.

### Planned (not yet implemented in runtime)
- Switch the default stdio runtime to `fastmcp` v2 (remove feature flag default-off behavior).
- Add a Codex-compatible “compat jobs” tool surface (submit/status/result/cancel/wait) for MCP hosts that do
  not implement SEP-1686.
- Default production guidance: decouple execution from the MCP server process by running work in external
  Docket workers by default (server concurrency=0, separate workers>0). (`gsd worker` exists; reference
  deployments and default guidance are still in progress.)
- MCP-compliant HTTP OAuth discovery/challenge surfaces (RFC 9728 `resource_metadata`, `WWW-Authenticate`
  semantics, step-up scopes, resource indicators / audience binding). (ADR-0013 Accepted; not implemented yet;
  spec: `gsd-browser/docs/api/FAST_MCP_V2_CANONICAL_SPEC.md` §9.)
- Expand the management/admin REST API (port 8081) with job inspection endpoints and wire CLI surfaces
  (e.g., `gsd tasks list`) to it.
  - Optionally also expose MCP tool wrappers for enumeration/inspection (proxying the same underlying
    identity-scoped logic), for clients that want a synchronous “list” workflow without using 8081.

## Minimum supported versions (for the Option B runtime)
- Python: `>=3.11` (this repo’s baseline)
- `fastmcp`: `>=2.14.3,<3.0`
- `mcp` (protocol types; transitive via `fastmcp`): `>=1.24.0,<2.0`
- Docket backend (transitive via `fastmcp`): `pydocket>=0.16.6`
- Redis/Valkey: `>=7.0` (Docket backend)
