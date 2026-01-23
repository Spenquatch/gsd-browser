# GSD MCP Tasks (long-running tools)

This document describes how `gsd` uses MCP long-running tasks (SEP-1686) for browser/agent tools.

## Status / migration boundary
This document describes task semantics for the FastMCP v2 runtime.
See `gsd-browser/docs/api/STATUS.md` for the implemented vs planned boundary and compatibility notes
(including stdio legacy vs v2 selection).

Canonical spec: `gsd-browser/docs/api/FAST_MCP_V2_CANONICAL_SPEC.md`.

## Scope
Tools that are long-running are configured as `taskSupport="required"` and must be invoked in task
mode. The task result payload returned by `tasks/result` is the same JSON schema described in
`gsd-browser/docs/api/MCP_TOOLS.md`.

## Protocol surface (MCP)
`gsd` relies on the standard MCP task methods:
- `tasks/get`: fetch task status
- `tasks/result`: fetch final tool result
- `tasks/cancel`: cancel a running task

Progress updates are sent via MCP progress notifications.

## Task TTL policy
- Server sets per-tool default TTLs appropriate for browser work (minutes, not seconds).
- Client TTL overrides are allowed only when explicitly enabled via a server env/config toggle and
  are bounded by server-configured min/max; out-of-range TTL is rejected.
- MCP protocol fields use **milliseconds** (`task.ttl`, `Task.pollInterval`); server config/env uses
  **seconds** and is converted.

This section is fully specified in `gsd-browser/docs/api/FAST_MCP_V2_CANONICAL_SPEC.md` (§3.3–§3.4).

### Concrete defaults (contract)
Defaults (server-chosen):
- `web_eval_agent`: 15 minutes (`900s`)
- `web_task_agent`: 30 minutes (`1800s`)
- `web_task_agent_github`: 30 minutes (`1800s`)

Bounds:
- Minimum TTL: 60 seconds
- Maximum TTL: 2 hours

Config knobs (names are part of the contract):
- `GSD_TASK_ALLOW_CLIENT_TTL_OVERRIDE` (bool, default false)
- `GSD_TASK_TTL_MIN_S` (int, default 60)
- `GSD_TASK_TTL_MAX_S` (int, default 7200)
- `GSD_TASK_TTL_WEB_EVAL_AGENT_S` (int, default 900)
- `GSD_TASK_TTL_WEB_TASK_AGENT_S` (int, default 1800)
- `GSD_TASK_TTL_WEB_TASK_AGENT_GITHUB_S` (int, default 1800)

## Polling + progress
- Server sets `Task.pollInterval` to a suggested value appropriate for browser work (default: 2s /
  2000ms).
- Progress notifications are emitted at least once per “agent step” and on key phase transitions.
- Progress is “best effort”:
  - if `max_steps` is known, progress should be step-based (completed steps out of `max_steps`)
  - otherwise, progress messages are informational with no stable percent semantics

This section is fully specified in `gsd-browser/docs/api/FAST_MCP_V2_CANONICAL_SPEC.md` (§6).

## Session vs identity
- Session IDs exist at the transport layer and may be used as an additional guard.
- Authorization for `tasks/get` and `tasks/result` is ultimately identity/tenant-scoped (task
  ownership is bound to authenticated claims), not “who knows the taskId”.

## Cancellation
Cancellation is treated as expected control flow:
- long-running tools must clean up browser sessions/pages on cancellation
- tasks should report final status promptly after cancellation

## Compatibility notes (important)
- The legacy SDK runtime (`mcp.server.fastmcp`) does not expose SEP-1686 tasks; it runs tools synchronously.
- The FastMCP v2 runtime makes long tools task-required, which requires an MCP host that supports SEP-1686.
  - For stdio, FastMCP v2 is currently gated behind `GSD_USE_FASTMCP_V2=true`.
  - For HTTP (`GSD_TRANSPORT=http`), `gsd` runs FastMCP v2 (Streamable HTTP).
  For MCP hosts that do not (e.g., current Codex-as-host usage), `gsd` will need a separate “compat job tools”
  surface (submit/status/result/cancel/wait). That surface is tracked in `docs/planning/BACKLOG.md`.
- `tasks/list` is intentionally not supported (method not found) to preserve non-enumerability semantics.
  - For task/job enumeration and operational visibility, Option B uses a separate management/admin REST API
    (port 8081), documented in `gsd-browser/docs/api/HTTP_API.md` and defined in ADR-0018 (Accepted).
  - If synchronous MCP clients need enumeration/inspection, expose it as **MCP tools** (not as the MCP
    protocol `tasks/list` method), ideally by sharing the same identity-scoped implementation used by the
    8081 management API.

### Cross-session “check later” support
SEP-1686 access is identity/tenant authorized and task lookup is session-independent:
- a task created in session A can be fetched/cancelled from session B (same identity), and
- HTTP can be configured as stateless so clients do not need to reuse `mcp-session-id` headers.

Design note:
- `tasks/get|result|cancel` uses the persisted task ownership record to locate the underlying task
  across sessions (see ADR-0012).
