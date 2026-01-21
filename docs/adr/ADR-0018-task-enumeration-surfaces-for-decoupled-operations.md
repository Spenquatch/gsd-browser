# ADR-0018: Task Enumeration Surfaces for Decoupled Operations

## Status
Proposed

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
Per ADR-0012, the MCP `tasks/list` method remains disabled (METHOD_NOT_FOUND). This avoids:
- Protocol ambiguity with immature MCP client implementations.
- Implicit coupling to MCP session semantics.
- Confusion about authorization model in MCP context.

### 2) Implement CLI task enumeration: `gsd tasks list`
Provide a CLI command for local/operator access:

```bash
# List tasks for current identity (from env/config)
gsd tasks list

# Filter by status
gsd tasks list --status running
gsd tasks list --status completed
gsd tasks list --status failed

# Filter by time range
gsd tasks list --since 1h
gsd tasks list --since 2024-01-15T00:00:00Z

# Show all tasks (admin mode - requires GSD_ADMIN_MODE=1 in server/prod)
gsd tasks list --all

# Output formats
gsd tasks list --format table   # default, human-readable
gsd tasks list --format json    # machine-readable
```

Identity resolution for CLI:
1. `GSD_TENANT_ID` + `GSD_SUBJECT_ID` environment variables (if set)
2. `~/.gsd/.env` configured identity
3. Fallback: `tenant_id=local`, `subject_id=$USER`

### 3) Implement HTTP API endpoint: `GET /api/v1/tasks`
Provide an HTTP endpoint for programmatic access:

```
GET /api/v1/tasks
Authorization: Bearer <jwt> | X-API-Key: <key>

Query parameters:
  status    - filter by task status (running|completed|failed|cancelled)
  since     - ISO-8601 timestamp or duration (1h, 30m, 7d)
  limit     - max results (default: 100, max: 1000)
  cursor    - pagination cursor for next page

Response:
{
  "tasks": [
    {
      "task_id": "...",
      "tool_name": "web_eval_agent",
      "status": "running",
      "created_at": "2024-01-15T10:30:00Z",
      "updated_at": "2024-01-15T10:31:00Z",
      "progress": { "current": 5, "total": 25 }
    }
  ],
  "next_cursor": "..."
}
```

Identity extraction from HTTP:
- JWT: `tenant_id` from `tid` claim, `subject_id` from `sub` claim
- API key: lookup in key registry → mapped identity
- Local development: configurable bypass with explicit identity headers

### 4) Identity scoping is mandatory
Both CLI and HTTP surfaces MUST filter results by caller identity:
- Query: `WHERE tenant_id = :caller_tenant AND subject_id = :caller_subject`
- No results from other identities are ever returned.
- `--all` flag (CLI) or admin scope (HTTP) requires explicit elevated privileges.

### 5) Non-enumerability across identity boundaries
Cross-identity enumeration remains impossible:
- Caller A cannot discover that Caller B has tasks.
- Empty result set is returned if no tasks match (not an error).
- No timing/count side channels that reveal other identities' task existence.

## Consequences

### Positive
- Operators can monitor and manage tasks without MCP client state.
- Decoupled architecture (Option B) becomes fully operational.
- Programmatic integration via HTTP enables dashboards, monitoring, CI/CD.
- Identity-scoped access preserves security model.

### Negative / Costs
- Two new surfaces to implement, test, and document.
- CLI must authenticate to Redis (connection string/credentials management).
- HTTP endpoint requires auth middleware (JWT validation or API key lookup).
- Potential for confusion: "why can't I use tasks/list in MCP?"

### Neutral
- MCP protocol behavior unchanged (tasks/list still disabled).
- Existing task ownership model (ADR-0012) remains authoritative.

## Implementation Notes

### CLI Implementation
- Add `gsd tasks` command group to `gsd_cli.py`.
- Query Redis directly using existing `TaskOwnershipStore`.
- Support `--format json` for scripting/piping.
- Consider `gsd tasks get <task_id>` and `gsd tasks cancel <task_id>` as well.

### HTTP Implementation
- Add `/api/v1/tasks` route to streaming server or dedicated API server.
- Reuse `TaskOwnershipStore` for queries.
- Implement cursor-based pagination for large result sets.
- Rate limiting recommended for production deployments.

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

### Admin mode (`--all`)
Admin listing is supported with environment-based gating:
- **Local development:** `--all` flag available by default (no restrictions).
- **Server/production:** Requires `GSD_ADMIN_MODE=1` environment variable to enable `--all`.
- Without the env var in production, `--all` returns an error indicating admin mode is disabled.

This allows developers full visibility locally while preventing accidental cross-tenant enumeration
in shared deployments.

### Real-time updates
WebSocket subscriptions for task status are **out of scope for v1**. Initial implementation focuses
on polling via CLI and HTTP. Real-time updates can be added in a future iteration.

### Retention window for listings
Task listing respects the retention policy defined in ADR-0017:
- Tasks are listable until they expire per the configured retention window.
- After expiry, tasks are not returned in listings (non-enumerable).
- Default retention windows (dev vs prod) are defined in ADR-0017.

## Open Questions
1. Should the HTTP endpoint live on the streaming server (port 5009) or a separate API server?
   This requires further research into operational topology and auth middleware placement.

## References
- ADR-0010: Decouple execution from MCP server + add compat job tools
- ADR-0012: Session-independent task lookup for SEP-1686 tasks
- ADR-0017: Job/Task retention and cleanup policy
- `gsd-browser/src/gsd_browser/optionb/task_ownership.py`
