# GSD MCP Tasks (long-running tools)

This document describes how `gsd` uses MCP long-running tasks (SEP-1686) for browser/agent tools.

## Status / migration boundary
This document describes the **target** task semantics for the FastMCP v2 migration on
`feat/fastmcp-v2-tasks`. See `gsd-browser/docs/api/STATUS.md` for what is implemented today.

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

### Concrete defaults (planned)
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

## Polling + progress (planned)
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
