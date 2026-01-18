# GSD MCP Tasks (long-running tools)

This document describes how `gsd` uses MCP long-running tasks (SEP-1686) for browser/agent tools.

## Scope
Tools that are long-running are configured as `taskSupport="required"` and must be invoked in task
mode. The task result payload returned by `tasks/result` is the same JSON schema described in
`docs/api/MCP_TOOLS.md`.

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

## Session vs identity
- Session IDs exist at the transport layer and may be used as an additional guard.
- Authorization for `tasks/get` and `tasks/result` is ultimately identity/tenant-scoped (task
  ownership is bound to authenticated claims), not “who knows the taskId”.

## Cancellation
Cancellation is treated as expected control flow:
- long-running tools must clean up browser sessions/pages on cancellation
- tasks should report final status promptly after cancellation

