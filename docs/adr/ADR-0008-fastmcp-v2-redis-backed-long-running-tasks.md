# ADR-0008: FastMCP v2 + Redis-backed MCP long-running tasks (SEP-1686)

## Status
Proposed

## Context
`gsd` exposes browser automation + agent workflows over MCP. Some tool calls are naturally long-running
(tens of seconds to minutes): opening a real website, waiting for JS, handling login state, running an
agent loop, collecting artifacts (screenshots, network/console excerpts), etc.

Today the MCP server is implemented using the official Python SDK’s `mcp.server.fastmcp`. While the
SDK includes task-related types and experimental hooks, we want a stable, end-to-end implementation of
the MCP long-running tasks protocol (SEP-1686) with:

- Immediate return of a `taskId` for long operations
- Progress reporting and status updates while work is running
- Cancellation support
- A deployment model that scales beyond a single process (separate workers; multiple replicas)

`jlowin/fastmcp` v2 provides a first-class implementation of the task protocol via Docket, including
server-side request handlers for `tasks/get`, `tasks/result`, `tasks/cancel`, and task-aware tool
execution modes.

## Decision
1) Adopt `jlowin/fastmcp` v2 as the MCP server framework for `gsd`.

2) Implement MCP long-running task support using FastMCP v2 background tasks:
- Mark long-running tools as task-capable (`TaskConfig(mode="optional", …)` by default).
- Use `ctx.report_progress(...)` (and/or the FastMCP `Progress` dependency) to provide user-visible
  progress for agent loops and browser steps.
- Make cancellation a first-class behavior; long-running tools must be cancellation-safe.

3) Use Redis/Valkey as the required Docket backend in “scale-ready” deployments:
- Configure Docket via `FASTMCP_DOCKET_URL=redis://…` (no `memory://` in production).
- Run background execution in dedicated worker processes, not only the embedded worker.

4) Transports:
- Keep `stdio` transport for local / desktop-hosted usage.
- Support a network transport (Streamable HTTP) for server deployments where the MCP host is remote.

## Consequences
### Positive
- Durable, protocol-native long-running tool execution (task IDs, polling, cancellation).
- Clear path to scale: multiple workers pulling tasks from Redis; multiple server replicas.
- Better UX: progress updates during long agent runs (instead of opaque timeouts).

### Negative / Costs
- New dependency surface and API changes from switching frameworks.
- Requires Redis/Valkey for “proper scaling” mode.
- Requires careful cleanup on cancellation to avoid leaking browser sessions/resources.

## Implementation Notes
- Dependency changes:
  - Add `fastmcp` (jlowin) v2 to `gsd-browser/pyproject.toml`.
  - Keep the MCP types dependency as required by FastMCP’s underlying protocol models.
- Tool execution modes:
  - Start with `optional` task support for `web_eval_agent`, `web_task_agent`, and
    `web_task_agent_github`.
  - Keep short, pure-query tools (`get_run_events`, `get_screenshots`) synchronous unless a concrete
    need emerges.
- Cancellation:
  - Treat cancellation as an expected control-flow path (likely `asyncio.CancelledError`).
  - Ensure browser contexts/pages are closed and any per-session state is finalized.
- Operational defaults:
  - Define default task TTL and poll intervals (server-suggested) appropriate for “browser work”.

## Open Questions
- Which tools (if any) should be `required` task execution vs `optional`?
- What task TTLs should be set by default, and should clients be able to override them?
- How should authorization apply to `tasks/get` and `tasks/result` for multi-tenant deployments?

## References
- MCP long-running tasks protocol (SEP-1686): `tasks/get`, `tasks/result`, `tasks/cancel`
- FastMCP v2 background tasks + Docket integration (jlowin/fastmcp)

