# GSD MCP API Status (canonical)

This file is the single source of truth for what is **implemented today** vs **planned** for the
FastMCP v2 (Option B) runtime.

## Implemented vs planned

### Implemented today (current runtime)
- MCP tools are available via the legacy SDK runtime (`mcp.server.fastmcp`) for stdio.
- A FastMCP v2 stdio entrypoint is implemented behind `GSD_USE_FASTMCP_V2=true`.
- FastMCP v2 requires Redis/Valkey via `FASTMCP_DOCKET_URL` (even on stdio).
- A FastMCP v2 HTTP (ASGI) entrypoint is implemented when `GSD_TRANSPORT=http` and JWT config is present.
- Tool responses follow the JSON payload schemas documented in `gsd-browser/docs/api/MCP_TOOLS.md`.
- SEP-1686 long-running tasks are implemented for long tools in the FastMCP v2 runtime:
  - long tools are task-required in v2
  - `tasks/get`, `tasks/result`, `tasks/cancel` handlers are active with ownership enforcement
  - progress notifications are emitted during agent work
- Distributed artifact storage is implemented (S3-compatible object store + Redis index) and is used when
  the required S3 env vars are configured.

### Implemented but not deployed
- **Artifact cleanup/retention enforcement**: `CleanupRunner` exists in `optionb/artifact_index.py` and is
  fully tested, but **no process currently schedules it**. S3 objects and Redis index entries will
  accumulate until a maintenance entrypoint is deployed. The canonical spec (§4.3 "Cleanup rules") documents
  this as "required", but the scheduling decision is blocked on ADR-0015 (which process leads maintenance?).
  - Operators requiring cleanup today must invoke `CleanupRunner.run_once()` manually or via external
    scheduling (cron, k8s CronJob, etc.).
  - See ADR-0015 (operational topology) and ADR-0017 (retention policy) for open questions.

### Planned (not yet implemented in runtime)
- Switch the default stdio runtime to `fastmcp` v2 (remove feature flag default-off behavior).
- Add a Codex-compatible “compat jobs” tool surface (submit/status/result/cancel/wait) for MCP hosts that do
  not implement SEP-1686.
- Decouple execution from the MCP server process by running work in external Docket workers by default
  (server concurrency=0, separate workers>0).
- MCP-compliant HTTP OAuth discovery/challenge surfaces (RFC 9728 `resource_metadata`, `WWW-Authenticate`
  semantics, step-up scopes, resource indicators / audience binding).
- Make “check later” task lookups independent of the current MCP session ID (identity-scoped access).

## Minimum supported versions (for the Option B runtime)
- Python: `>=3.11` (this repo’s baseline)
- `fastmcp`: `>=2.14.3,<3.0`
- `mcp` (protocol types; transitive via `fastmcp`): `>=1.24.0,<2.0`
- Docket backend (transitive via `fastmcp`): `pydocket>=0.16.6`
- Redis/Valkey: `>=7.0` (Docket backend)
