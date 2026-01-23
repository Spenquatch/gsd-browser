# GSD HTTP Management API (planned)

This document describes the **management/admin REST API** intended for Option B operations
visibility (task/job enumeration and inspection). This is **not** the MCP protocol surface.

Status:
- The canonical implemented-vs-planned boundary is `gsd-browser/docs/api/STATUS.md`.
- The management/admin REST API is defined as part of the architecture in ADR-0018, but may not be
  fully implemented yet.

## Purpose and ports
The Option B runtime uses three distinct HTTP surfaces:
- **5009**: streaming/dashboard server (Socket.IO, CDP control, take-control UX)
- **8080**: MCP over HTTP transport (Streamable HTTP MCP; tool invocation; not REST)
- **8081**: management/admin REST API (this document)

ADR: `docs/adr/ADR-0018-task-enumeration-surfaces-for-decoupled-operations.md`.

## Audience
This REST API is intended for:
- the CLI (`gsd tasks list`, `gsd jobs get`, etc.)
- monitoring/observability tools
- dashboards and operations workflows

It is not intended as a general “client API” for browser automation; MCP tool calls belong on the
MCP transport (8080) instead.

## Auth model (invariants)
The management API is security-sensitive because it provides *enumeration* and *inspection*.

Contract-level invariants (must hold):
- Identity extraction for 8081 MUST match 8080 (same tenant/subject rules), so callers cannot be
  “a different user” depending on which port they hit.
- All endpoints are identity-scoped by default (`tenant_id` + `subject_id`).
- Admin/all-identities access is disabled by default and requires explicit gating + audit logging.
- Unauthorized vs nonexistent vs expired resources should be non-enumerable for non-admin callers
  (prefer “not found” semantics).

See:
- ADR-0018 (surface split + auth invariants)
- ADR-0014 (local HTTP hardening guidance)
- ADR-0013 (MCP/OAuth discovery/challenge surfaces; applies primarily to MCP HTTP, but the same JWT
  verification policy should be reused here)

### Authentication mechanisms
Planned supported mechanisms:
- `Authorization: Bearer <jwt>` (primary; multi-tenant)
- `X-API-Key: <key>` (optional; for automation/ops tooling; maps to an identity)

## Endpoints (planned)

### List tasks
`GET /api/v1/tasks`

Query parameters (example set):
- `status`: `running|completed|failed|cancelled` (optional)
- `since`: ISO-8601 timestamp or duration (`1h`, `30m`, `7d`) (optional)
- `limit`: default 100, max 1000
- `cursor`: pagination cursor (opaque)

Response (example shape):
```json
{
  "tasks": [
    {
      "task_id": "…",
      "tool_name": "web_eval_agent",
      "status": "running",
      "created_at": "2026-01-21T12:34:56Z",
      "updated_at": "2026-01-21T12:35:12Z"
    }
  ],
  "next_cursor": "…"
}
```

### Get job details
`GET /api/v1/jobs/{job_id}`

Notes:
- `job_id` refers to the compat jobs contract (ADR-0011).
- This endpoint is for ops/inspection; compat job interaction for MCP clients happens via MCP tools
  on port 8080.

## Error semantics (recommended)
For non-admin callers:
- Missing/invalid auth: `401 Unauthorized`
- Authenticated but insufficient scope: `403 Forbidden` (if using scopes)
- Unauthorized resource (wrong tenant/subject), nonexistent, or expired: return “not found”
  semantics (avoid distinguishability)

For admin callers (explicitly gated):
- Prefer explicit `403` vs `404` for observability when appropriate, but keep defaults strict.

## Test checklist (conformance)
- Same identity:
  - can list tasks/jobs within retention window
  - can fetch details for owned job IDs
- Cross-tenant/subject:
  - listing returns empty and does not leak existence
  - get-by-id is non-enumerable (does not distinguish unauthorized vs nonexistent)
- Admin gating:
  - disabled by default
  - when enabled, is auditable and requires explicit scopes/config

