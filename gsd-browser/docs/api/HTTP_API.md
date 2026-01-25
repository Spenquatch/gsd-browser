# GSD HTTP Management API (8081) — v1 Contract

This document pins the **v1 contract** for the Option B management/admin REST API. This is **not**
the MCP protocol surface (8080).

Status:
- The canonical implemented-vs-planned boundary is `gsd-browser/docs/api/STATUS.md`.
- The 8081 REST API is defined as part of the architecture in ADR-0018 and is documented here as a
  stable contract for the CLI and operators.

ADR: `docs/adr/ADR-0018-task-enumeration-surfaces-for-decoupled-operations.md`.

## Purpose and ports
The Option B runtime uses three distinct HTTP surfaces:
- **5009**: streaming/dashboard server (Socket.IO, CDP control, take-control UX)
- **8080**: MCP over HTTP transport (Streamable HTTP MCP; tool invocation; not REST)
- **8081**: management/admin REST API (this document)

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
- Admin (cross-identity) access is disabled by default and requires explicit gating + audit logging.
- Unauthorized vs nonexistent vs expired resources should be non-enumerable for non-admin callers
  (prefer “not found” semantics for get-by-id).

See:
- ADR-0018 (surface split + auth invariants)
- ADR-0014 (local HTTP hardening guidance)
- `gsd-browser/docs/api/FAST_MCP_V2_CANONICAL_SPEC.md` (identity mapping + non-enumerability rules)

### Authentication mechanisms
Supported mechanisms (v1):
- `Authorization: Bearer <jwt>` (primary; multi-tenant)
- `X-API-Key: <key>` (optional; ops automation; maps to an identity and scopes)

### Scope extraction (pinned)
Scope extraction is pinned as:
- Prefer JWT claim `scope` (string; space-separated), fallback to `scp` (array of strings or
  space-separated string).
- Any invalid scope claim format results in “no scopes”.

Scope-gated endpoints (v1; pinned):
- `GET /api/v1/tasks`: requires `gsd:browser:read` OR `gsd:admin`
- `GET /api/v1/admin/tasks`: requires `gsd:admin` (and admin enablement; see endpoint section)

### Identity extraction (pinned)
HTTP identity is derived from JWT claims using the canonical mapping in
`gsd-browser/docs/api/FAST_MCP_V2_CANONICAL_SPEC.md` (§1):
- `tenant_id` claim name: `GSD_JWT_TENANT_ID_CLAIM` (default `tenant_id`)
- `subject_id` claim name: `GSD_JWT_SUBJECT_ID_CLAIM` (default `sub`)

### API keys (pinned)
API keys are enabled only when `GSD_API_KEYS_FILE` is set.

Request header:
- `X-API-Key: <key>`

File format:
- JSON array of entries. Each entry maps to an identity and scopes:
  - `tenant_id` (string)
  - `subject_id` (string)
  - `scopes` (string[])
  - either:
    - `key` (string) — plaintext (recommended only for local/dev), or
    - `key_sha256` (string) — hex SHA-256 of the key (recommended for production)
  - optional `label` and `created_at` for audit

Example:
```json
[
  {
    "label": "ops-bot",
    "created_at": "2026-01-24T00:00:00Z",
    "key_sha256": "…",
    "tenant_id": "tenant_a",
    "subject_id": "ops_bot",
    "scopes": ["gsd:admin"]
  }
]
```

## Pagination + sorting (pinned)
Ordering is fixed in v1:
- Sort by `created_at desc` (tie-break by `task_id desc`)

Pagination is cursor-based:
- Request: `cursor=<opaque>`
- Response: `next_cursor=<opaque|null>`

Cursor invariants:
- Cursors are **opaque** (clients must not parse them).
- A cursor is **bound to the query parameters** used to generate it. Reusing a cursor with different
  filters must return `400` with `error.code="invalid_cursor"`.

## Errors (pinned)
All error responses use a stable JSON envelope:
```json
{
  "error": {
    "code": "invalid_cursor",
    "message": "Cursor does not match query",
    "details": { "hint": "Do not reuse cursors across filters." }
  }
}
```

Status code guidance:
- `400` invalid inputs (`invalid_cursor`, `invalid_query`, `invalid_limit`, `invalid_since`, …)
- `401` missing/invalid authentication
- `403` authenticated but:
  - insufficient scope, or
  - admin endpoints disabled
- `404` not found (used to preserve non-enumerability for get-by-id when unauthorized/nonexistent/expired)

## Endpoints (v1)

### Health
`GET /healthz`

Returns a small JSON object suitable for liveness/readiness checks.

### List tasks (identity-scoped)
`GET /api/v1/tasks`

Authorization:
- Requires `gsd:browser:read` OR `gsd:admin` scope.

Query parameters:
- `limit` (int, optional): default `100`, max `1000`
- `cursor` (string, optional): opaque pagination cursor
- `status` (string, optional): `queued|running|completed|failed|cancelled`
- `tool_name` (string, optional): comma-separated tool names (example: `web_eval_agent,web_task_agent`)
- `since` (string, optional): RFC 3339 timestamp (preferred) or duration (`30m`, `7d`)

Response:
```json
{
  "tasks": [
    {
      "task_id": "…",
      "tool_name": "web_eval_agent",
      "status": "running",
      "created_at": "2026-01-24T18:12:03Z",
      "updated_at": null,
      "expires_at": "2026-01-24T18:27:03Z",
      "session_id": "…"
    }
  ],
  "next_cursor": "…"
}
```

Field notes:
- `updated_at` MAY be `null` if the backend does not provide a reliable “last updated” timestamp.
- `expires_at` is the task ownership/visibility expiry, not necessarily the backend task TTL.

### List tasks (admin; cross-identity)
`GET /api/v1/admin/tasks`

Gating (both required):
- Server: admin mode enabled (for example `GSD_ADMIN_MODE=1`)
- Caller: authorized for `gsd:admin` scope

Query parameters:
- All params from `GET /api/v1/tasks`, plus:
  - `tenant_id` (string, optional)
  - `subject_id` (string, optional)
  - `transport` (string, optional): `stdio|http`

Response:
```json
{
  "tasks": [
    {
      "task_id": "…",
      "tool_name": "web_eval_agent",
      "status": "running",
      "created_at": "2026-01-24T18:12:03Z",
      "updated_at": null,
      "expires_at": "2026-01-24T18:27:03Z",
      "session_id": "…",
      "tenant_id": "…",
      "subject_id": "…",
      "transport": "http"
    }
  ],
  "next_cursor": "…"
}
```

### Get job details (planned; contract placeholder)
`GET /api/v1/jobs/{job_id}`

Notes:
- `job_id` refers to the compat jobs contract (ADR-0011).
- This endpoint is for ops/inspection; compat job interaction for MCP clients happens via MCP tools
  on port 8080.

## Conformance checklist (v1)
- Same identity:
  - can list tasks within retention window
  - can filter and paginate deterministically
- Cross-tenant/subject:
  - listing never leaks other identities
  - get-by-id remains non-enumerable for non-admin callers
- Admin gating:
  - disabled by default
  - when enabled, requires `gsd:admin` and emits audit logs
