# GSD MCP API Status (canonical)

This file is the single source of truth for what is **implemented today** vs **planned** for the
FastMCP v2 (Option B) migration on `feat/fastmcp-v2-tasks`.

## Implemented vs planned

### Implemented today (current runtime)
- MCP tools are served by the official Python SDK (`mcp.server.fastmcp`).
- Tool responses follow the JSON payload schemas documented in `gsd-browser/docs/api/MCP_TOOLS.md`.
- `get_screenshots` includes “presigned-url-ready” placeholders under `screenshots[].artifact`
  (`key=<screenshot id>`, `url=null`) but does not yet use a distributed artifact store.

### Planned (not yet implemented in runtime)
- Framework migration to `fastmcp` v2 (`jlowin/fastmcp`).
- SEP-1686 long-running tasks for long tools (`taskSupport="required"`), including:
  `tasks/get`, `tasks/result`, `tasks/cancel`, and progress notifications.
- Redis/Valkey-backed task queue via Docket (FastMCP background tasks).
- Distributed artifact storage (S3-compatible object store + Redis index).
  - Self-hosted reference: SeaweedFS (S3 gateway). AWS S3 is also supported.
- Tenant/identity-scoped authorization boundaries for task + artifact access.

## Minimum supported versions (for the planned Option B runtime)
- Python: `>=3.11` (this repo’s baseline)
- `fastmcp`: `>=2.14.3,<3.0`
- `mcp` (protocol types; transitive via `fastmcp`): `>=1.24.0,<2.0`
- Docket backend (transitive via `fastmcp`): `pydocket>=0.16.6`
- Redis/Valkey: `>=7.0` (Docket backend)
