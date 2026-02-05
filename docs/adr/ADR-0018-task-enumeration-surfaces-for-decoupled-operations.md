# ADR-0018: Task Enumeration Surfaces for Decoupled Operations

## Status
Accepted

## Context
ADR-0012 disabled `tasks/list` in the MCP protocol to preserve non-enumerability semantics. The
rationale was sound for an MCP-only world: callers remember task IDs and retrieve them later.

However, the Option B architecture (ADR-0010) decouples task execution from MCP client sessions:
- Workers run independently of the MCP server process.
- Tasks survive MCP client disconnection/restart.
- MCP clients may lose state (crash, restart, new session).
- CLI operators need visibility into running/completed tasks.
- Most MCP clients do not yet support long-lived tasks (SEP-1686).

The "caller remembers" model breaks when:
1. MCP client session dies and loses the task ID.
2. User starts a new CLI/MCP session and wants to check on prior tasks.
3. Operator needs to monitor/manage tasks across sessions.
4. Different tool/client wants to access tasks started by another.

A task enumeration surface is required, but it must:
- Remain identity-scoped (tenant + subject) to preserve authorization boundaries.
- Be non-enumerable across identity boundaries (no cross-tenant/subject discovery).
- Work independently of MCP protocol limitations.

## Decision

### 1) Keep `tasks/list` disabled in MCP protocol
Per ADR-0012, the MCP `tasks/list` method remains disabled (METHOD_NOT_FOUND).

Task enumeration is an operations surface with sharp security semantics (enumerability, pagination,
multi-tenant scoping). We do not treat MCP protocol `tasks/list` as the durable, supported listing
mechanism for Option B.

### 2) Three HTTP surfaces with distinct purposes (the full picture)
Option B needs three separate HTTP surfaces with different protocols, auth, and use cases.

#### A) Port 5009: Streaming/Dashboard server (browser visualization/control)
- Browser control (CDP)
- Visual dashboard for watching agents work
- Take-control feature
- Socket.IO streaming
- Purpose: browser visualization/control

#### B) Port 8080: MCP HTTP transport (MCP protocol over HTTP; not REST)
- MCP protocol over HTTP (Streamable HTTP; **not** a REST API).
- Exposes all MCP tools via HTTP transport:
  - Native tools (examples): `web_eval_agent`, `setup_browser_state`, `get_run_events`, `get_screenshots`
  - Compat job tools (examples; when implemented): `web_eval_agent_submit`, `job_get`, `job_wait`, etc.
- For: MCP clients that can't do stdio and/or don't support SEP-1686.
- JWT auth required (multi-tenant).
- Identity propagation to workers required when execution is detached.
- Purpose: broad MCP client support (HTTP-based MCP clients).

#### C) Port 8081: Management/Admin REST API (operations visibility; not MCP)
- Regular REST API (**not** the MCP protocol).
- Task/job enumeration and inspection endpoints (example shapes):
  - `GET /api/v1/tasks` (task listing)
  - `GET /api/v1/jobs/{job_id}` (job details)
- For:
  - CLI: `gsd tasks list`
  - monitoring tools
  - dashboards
  - operational visibility / audits
- Auth: JWT and/or API key (operator/automation friendly).
- Purpose: task enumeration outside of MCP protocol.

### 3) Why we need both 8080 (MCP) and 8081 (REST)
Port 8080 (MCP HTTP):
- MCP protocol clients connect here.
- They submit/check long work via MCP tool calls.
- Example: `job_wait(job_id="abc")` via MCP protocol over HTTP.

Port 8081 (REST API):
- Non-MCP clients connect here.
- Plain HTTP REST for operations/monitoring.
- Example: `curl http://localhost:8081/api/v1/tasks`.
- CLI uses this surface for listing/ops visibility, not MCP protocol methods.

### 4) Identity scoping and non-enumerability are mandatory (all listing surfaces)
Both the management REST API and any CLI surfaces MUST filter results by caller identity:
- Query: `WHERE tenant_id = :caller_tenant AND subject_id = :caller_subject`
- No results from other identities are ever returned.
- “Admin/all identities” mode requires explicit elevated privileges and must be safe-by-default.

Cross-identity enumeration remains impossible:
- Caller A cannot discover that Caller B has tasks.
- Empty result set is returned if no tasks match (not an error).
- Avoid timing/count side channels that reveal other identities' task existence.

### 4.1) AuthZ invariants across ports (contract-level)
To avoid drift and accidental cross-tenant leakage, the following invariants MUST hold across all three
surfaces (5009/8080/8081):

- **Consistent identity extraction**:
  - 8080 (MCP HTTP) and 8081 (management REST) MUST derive `tenant_id` + `subject_id` from the same
    JWT claims/mapping rules (or the same API-key → identity mapping), so “who am I?” is consistent.
- **Default-deny + strict scoping**:
  - All “list” and “get by id” operations on 8081 MUST be identity-scoped by default.
  - No cross-tenant/subject reads are allowed without explicit, auditable admin configuration.
- **Safe-by-default admin gating**:
  - “admin/all identities” access is disabled by default and requires explicit configuration + scopes.
  - Admin access must be observable (audit logging) and must not be reachable accidentally.
- **Non-enumerability semantics are consistent**:
  - Unknown vs unauthorized vs expired should not be distinguishable to non-admin callers. Prefer
    non-enumerable “not found” behavior.
- **Local-hardening expectations apply when exposed to browsers**:
  - If 5009 and/or 8081 are reachable from a browser context, apply local HTTP hardening (Origin/Host
    validation, bind defaults, and secret redaction) per ADR-0014.

### 5) Transports summary (what connects where)
- STDIO MCP: `gsd mcp serve` (local dev convenience).
- HTTP MCP: port 8080 (broad client support; non-SEP-1686 support via compat job tools).
- REST API: port 8081 (CLI, monitoring, dashboards; task enumeration outside of MCP).

## Consequences

### Positive
- Clear separation of concerns across protocols and ports (streaming UI vs MCP transport vs ops REST).
- Operators can enumerate/monitor/manage tasks without relying on MCP client state.
- HTTP MCP remains focused on tool invocation, not ops-grade enumeration semantics.
- Identity-scoped access preserves the security model.

### Negative / Costs
- More surfaces to implement, test, and document (MCP HTTP + management REST + streaming server).
- Auth middleware must be consistently applied (JWT and/or API keys) with clear operator guidance.
- Potential for confusion: “why can't I use `tasks/list` in MCP?” (answer: use REST management API).

### Neutral
- MCP protocol behavior unchanged (tasks/list still disabled).
- Existing task ownership model (ADR-0012) remains authoritative.

## Implementation Notes

### CLI implementation
- `gsd tasks list` uses the management REST API (port 8081), not MCP `tasks/list` and not direct Redis
  access by default.
- Support `--format json` for scripting/piping.

### MCP HTTP transport implementation (port 8080)
- Expose Streamable HTTP MCP (FastMCP v2) with JWT auth and identity propagation invariants.
- Compat jobs tool surface (ADR-0011) is the preferred non-SEP-1686 long-running path for HTTP MCP.

### Management REST API implementation (port 8081)
- Implement `/api/v1/tasks` and `/api/v1/jobs/{job_id}` (and related ops endpoints as needed).
- Use cursor-based pagination and bounded limits.
- Rate limiting recommended for production deployments.
- Implementation pattern (pinned):
  - Implement listing/inspection as a shared internal service layer.
  - 8081 REST endpoints and MCP wrapper tools (if exposed) MUST call the same service layer.
  - MCP wrapper tools must not depend on loopback HTTP calls to 8081.

### Redis Query Pattern
```python
# Pseudocode for identity-scoped listing
keys = redis.scan(match="task:ownership:*")
tasks = []
for key in keys:
    record = redis.hgetall(key)
    if record["tenant_id"] == caller.tenant_id and record["subject_id"] == caller.subject_id:
        tasks.append(record)
# Apply status/time filters, sort by created_at desc
```

Consider adding a secondary index for efficient listing:
```
task:by_identity:{tenant_id}:{subject_id} -> ZSET of task_ids by created_at
```

### Documentation Updates
- Update `docs/api/FAST_MCP_V2_CANONICAL_SPEC.md` to reference CLI/HTTP surfaces.
- Add CLI reference to `gsd-browser/docs/CLI.md` (or create if missing).
- Add HTTP API reference to `gsd-browser/docs/api/HTTP_API.md` (or create).

## Decisions on Scope

### Admin listing (cross-identity)
Admin listing is supported but **safe-by-default**:
- Use explicit admin endpoints (e.g., `/api/v1/admin/*`) rather than overloading the default identity-scoped endpoints.
- Admin endpoints require BOTH:
  - explicit server enablement (for example `GSD_ADMIN_MODE=1`), AND
  - caller authorization via `gsd:admin` scope (JWT scope claim or API-key scopes).
- Admin access must be auditable (structured logs).

### Real-time updates
WebSocket subscriptions for task status are **out of scope for v1**. Initial implementation focuses
on polling via CLI and HTTP. Real-time updates can be added in a future iteration.

### Retention window for listings
Task listing respects the retention policy defined in ADR-0017:
- Tasks are listable until they expire per the configured retention window.
- After expiry, tasks are not returned in listings (non-enumerable).
- Default retention windows (dev vs prod) are defined in ADR-0017.

## Open Questions
None (for this ADR). Ports and responsibilities are explicitly split across the three surfaces.

## References
- ADR-0010: Decouple execution from MCP server + add compat job tools
- ADR-0012: Session-independent task lookup for SEP-1686 tasks
- ADR-0017: Job/Task retention and cleanup policy
- `gsd-browser/src/gsd_browser/optionb/task_ownership.py`
