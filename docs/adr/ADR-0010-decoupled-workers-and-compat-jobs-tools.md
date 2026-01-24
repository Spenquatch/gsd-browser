# ADR-0010: Decouple execution from MCP server + add compat job tools

## Status
Accepted

## Context
`gsd` is used from MCP hosts with different capability levels.

- Some MCP hosts (including current Codex-as-host usage) do **not** implement SEP-1686 task-augmented
  execution (`taskSupport`, `tasks/get`, `tasks/result`, `tasks/cancel`).
- MCP stdio servers launched by hosts are typically subprocesses managed by the host. If the host
  restarts, reloads config, or drops the connection, the server process can be terminated.
- `gsd`’s long-running tools can take minutes and produce artifacts over time (screenshots, run-events).

Goal: support **client-independent** long jobs:
- jobs must keep running even if the MCP host session ends
- jobs must be checkable later (status + results + progress/artifacts)
- keep the “native” MCP long-running tasks path (SEP-1686) for hosts that support it

## Decision

### 0) Session independence is a hard requirement (both paths)
After decoupling execution into external workers, a long-running unit of work (job/task) MUST be
retrievable from a new MCP server instance / a new host session, provided the caller’s identity
matches the persisted ownership record.

This requirement applies to:
- the compat jobs surface (regular tools), and
- the SEP-1686 task surface (`tasks/get|result|cancel`) when feasible.

### 1) Run execution in a separate worker process
Adopt the FastMCP/Docket scale pattern:
- MCP server processes run with `FASTMCP_DOCKET_CONCURRENCY=0` so they **do not execute** tasks.
- One or more long-lived worker processes run separately (against the same Redis backend):
  - share `FASTMCP_DOCKET_URL` and `FASTMCP_DOCKET_NAME`
  - execute queued work and persist results/artifacts

This makes task execution durable and independent of the MCP host lifecycle.

### 2) Add “compat job tools” for non-SEP-1686 MCP hosts
Add a second surface for long work that uses **regular tools** (no SEP-1686 required):
- `*_submit(...)` returns a `job_id` immediately
- `job_get(job_id)` returns status + progress snapshot
- `job_result(job_id)` returns the final tool payload when ready
- `job_cancel(job_id)` cancels the job
- optional `job_wait(job_id, max_wait_s, poll_interval_s)` (wait-but-don’t-cancel convenience)

These tools will be the primary integration path for Codex today, while preserving the canonical
SEP-1686 path for hosts that support it.

### 3) Identity propagation for detached worker execution (HTTP)
For HTTP transport, request auth context is not automatically available inside detached workers.
To preserve multi-tenant boundaries:
- identity (`tenant_id`, `subject_id`, transport) MUST be explicitly persisted with the job/task and
  re-established inside the worker execution path (enter `identity_scope(...)`).
- stdio remains `tenant_id=local`, `subject_id=local` and can defer the explicit propagation work.

## Consequences

### Positive
- Long jobs survive MCP host restarts / config reloads (Codex-compatible).
- Enables true horizontal scaling (multiple workers consuming from Redis).
- Provides a stable “submit + poll” UX even without SEP-1686 support in the host.

### Negative / Costs
- Requires an operator-visible worker process (systemd/Docker/etc).
- Requires additional API surface (job tools) and careful compatibility documentation.
- Adds complexity for HTTP multi-tenant: must propagate identity into worker execution explicitly.

## Implementation Notes
- Provide a documented and scripted worker entrypoint for `gsd` (not a bespoke manual command).
  - Define recommended env defaults for `FASTMCP_DOCKET_NAME` and concurrency split.
  - Clarify deployment shapes:
    - local dev: `FASTMCP_DOCKET_CONCURRENCY>0` (embedded worker) allowed
    - production: server concurrency `0`, external workers `>0`
- Compat job tools should not depend on the MCP session ID being stable across calls.
  - Store enough mapping/metadata to locate the underlying execution and enforce authorization.
- For HTTP: explicitly include tenant/subject identity in the queued job input or in an ownership
  record that workers consult before executing.
- Keep the native SEP-1686 path intact for MCP hosts that support it.

## Acceptance / conformance
- Start stdio server, submit long job, kill stdio server process: job continues (worker). Later start a
  new server instance and `job_get`/`job_result` succeeds.
- Same identity can fetch; different tenant/subject gets a non-enumerable “not found”.
- (Optional) The SEP-1686 `tasks/get|result|cancel` path also works across server restart / new session.

## Resolved Questions
- Compat jobs contract/IDs/progress surface: ADR-0011 (Accepted).
- Session-independent task lookup for SEP-1686: ADR-0012 (Accepted).
- MCP-compliant HTTP auth surfaces (OAuth discovery/challenges/scopes): ADR-0013 (Accepted).

## References
- ADR-0008: FastMCP v2 + Redis-backed MCP long-running tasks (SEP-1686)
- ADR-0009: Distributed artifact storage for scaled task execution
- ADR-0011: Compat job tools contract and job ID strategy
- ADR-0012: Session-independent task lookup for SEP-1686 tasks
- ADR-0013: MCP-compliant HTTP authorization surfaces and scope model
- `docs/planning/BACKLOG.md`
- `gsd-browser/docs/api/FAST_MCP_V2_CANONICAL_SPEC.md`
