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
- A supported external worker entrypoint exists for Option B via `gsd-browser worker`:
  - Server process can be run with `FASTMCP_DOCKET_CONCURRENCY=0` (does not execute tasks).
  - Worker process(es) can be run with `FASTMCP_DOCKET_CONCURRENCY>0` (executes queued work).
  - Both must share the same Docket backend (`FASTMCP_DOCKET_URL`, `FASTMCP_DOCKET_NAME`).
  - Example (two-process topology):
    - `GSD_USE_FASTMCP_V2=true FASTMCP_DOCKET_CONCURRENCY=0 gsd mcp serve`
    - `FASTMCP_DOCKET_URL=redis://localhost:6379/0 FASTMCP_DOCKET_CONCURRENCY=4 gsd-browser worker`
- Reference deployments (docker compose; ADR-0015):
  - Minimal (server + worker + redis): `gsd-browser/docker/compose.minimal.yml`
    - `docker compose -f gsd-browser/docker/compose.minimal.yml up --build`
    - `docker compose -f gsd-browser/docker/compose.minimal.yml down -v`
  - Production-ready (server + worker pool + redis + SeaweedFS): `gsd-browser/docker/compose.production.yml`
    - `docker compose -f gsd-browser/docker/compose.production.yml up --build --scale gsd-worker=3`
    - `docker compose -f gsd-browser/docker/compose.production.yml down -v`
  - Note: these reference compose files include placeholder JWT settings; for real HTTP usage you must set
    `GSD_JWT_JWKS_URL`, `GSD_JWT_ISSUER`, and `GSD_JWT_AUDIENCE` (see `gsd-browser/docs/api/FAST_MCP_V2_CANONICAL_SPEC.md` §8.3).
- Tool responses follow the JSON payload schemas documented in `gsd-browser/docs/api/MCP_TOOLS.md`.
- SEP-1686 long-running tasks are implemented for long tools in the FastMCP v2 runtime:
  - long tools are task-required in v2
  - `tasks/get`, `tasks/result`, `tasks/cancel` handlers are active with ownership enforcement
  - task lookup is session-independent (create in one session, fetch/cancel in another) via persisted
    ownership records (ADR-0012 Accepted)
  - progress notifications are emitted during agent work
- Compat jobs are partially implemented for non-SEP-1686 clients (ADR-0011):
  - `{tool}_submit` tools (`web_eval_agent_submit`, `web_task_agent_submit`, `web_task_agent_github_submit`)
  - `job_get` (state/progress snapshot)
- Distributed artifact storage is implemented (S3-compatible object store + Redis index) and is used when
  the required S3 env vars are configured.
- Worker-led artifact cleanup/retention enforcement is scheduled in `gsd worker` using the distributed lock
  defined in the canonical spec (§4.3) and the `GSD_CLEANUP_INTERVAL_S` interval (ADR-0015).
- A management/admin REST API (port 8081) is implemented (ADR-0018):
  - `/healthz`
  - `GET /api/v1/tasks` (identity-scoped)
  - `GET /api/v1/admin/tasks` (admin-gated; requires `GSD_ADMIN_MODE=1` + `gsd:admin`)

### Planned (not yet implemented in runtime)
- Switch the default stdio runtime to `fastmcp` v2 (remove feature flag default-off behavior).
- Finish the compat jobs tool surface (`job_result`, `job_cancel`, `job_wait`) for MCP hosts that do not implement SEP-1686.
- Default production guidance: decouple execution from the MCP server process by running work in external
  Docket workers by default (server concurrency=0, separate workers>0). (Reference deployments exist under
  `gsd-browser/docker/compose.*.yml`; see “Implemented today”.)
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
