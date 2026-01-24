# ADR-0012: Session-independent task lookup for SEP-1686 tasks

## Status
Accepted

## Context
FastMCP v2 implements SEP-1686 tasks (`tasks/get|result|cancel`) using a Redis-backed Docket store.
In practice, parts of the task metadata and/or lookup keys can be coupled to the MCP transport
session (`mcp-session-id`).

That coupling is at odds with the “check later” requirement:
- hosts may not reuse the same session ID after reconnect/restart,
- stdio servers can be restarted by the host,
- HTTP servers can be restarted/rescheduled,
- callers should be able to retrieve a task from a new server instance/new session as long as their
  identity matches task ownership.

ADR-0010 makes session independence a hard requirement and calls out that this requirement applies
to SEP-1686 tasks as well (when feasible).

## Decision

### 1) Treat identity as the authorization boundary for task lookup
For `tasks/get|result|cancel`:
- `taskId` is not an authorization boundary.
- The caller’s identity (tenant + subject) MUST match the persisted ownership record.
- On authorization failure, prefer non-enumerable “not found” behavior (unless explicitly configured
  otherwise).

### 2) Make `tasks/get|result|cancel` independent of the current transport session
Where the underlying task store/handlers would otherwise require the *current* `mcp-session-id` to
match the originating one, `gsd` MUST provide session-independent lookup by:
- persisting an ownership/mapping record keyed by `taskId`, and
- using that record to locate the underlying task storage key regardless of the current session ID.

This enables “create in session A, fetch in session B” workflows for SEP-1686 tasks.

### 3) Task enumeration (`tasks/list`) is not required for "check later" in MCP
To preserve non-enumerability and reduce MCP protocol surface area:
- do not depend on `tasks/list` for core MCP workflows.

Decision: disable `tasks/list` in MCP protocol (method not supported). For decoupled operations
where callers need task enumeration, see ADR-0018 which defines CLI (`gsd tasks list`) and HTTP
(`GET /api/v1/tasks`) surfaces with identity-scoped access.

## Consequences

### Positive
- SEP-1686 tasks become compatible with real-world host/session restart behavior.
- Aligns task semantics with the compat jobs contract (session independence + identity-scoped authZ).

### Negative / Costs
- May require overriding FastMCP’s default task protocol handlers or introducing additional
  indirection records, depending on upstream keying behavior.
- Adds more “durability plumbing” to maintain and test.

## Implementation Notes
- Implemented by persisting TaskOwnershipRecord (keyed by `taskId`) and using the stored `session_id` to temporarily bind FastMCP task protocol handler lookups to the originating session.
- See: `gsd-browser/src/gsd_browser/optionb/fastmcp_server.py` (`_setup_task_protocol_handlers`).
- Persist per-task ownership/mapping records with at least:
  - `taskId`, `tool_name`, `tenant_id`, `subject_id`, `created_at`, `expires_at`,
  - any backend-specific locator needed to fetch status/result/cancel from a new session.
- Add conformance tests:
  - create task in session A, then `tasks/get`/`tasks/result` in session B succeeds (same identity)
  - cross-tenant/subject access is non-enumerable

## Open Questions
### Fallback if task protocol handlers cannot be overridden
**Decision (2026-01-24):** Session-independent SEP-1686 “check later” support remains a hard
requirement for the Option B runtime.

If FastMCP upstream changes make handler override impractical, the fallback is **fail-fast** (not
silent degradation): the Option B runtime must refuse to start (or must explicitly disable v2 and
surface a clear error) rather than accepting session-dependent lookup behavior.

## References
- ADR-0008: FastMCP v2 + Redis-backed MCP long-running tasks (SEP-1686)
- ADR-0010: Decouple execution from MCP server + add compat job tools
- ADR-0018: Task enumeration surfaces for decoupled operations
- `docs/planning/BACKLOG.md`
