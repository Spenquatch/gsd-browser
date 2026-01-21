# ADR-0011: Compat job tools contract and job ID strategy

## Status
Proposed

## Context
Some MCP hosts (notably current Codex-as-host usage) do not implement SEP-1686 tasks. For those hosts,
`gsd` needs a “regular tools” surface that supports client-independent long work:
- submit work and get an identifier immediately,
- check status/progress later,
- fetch results later,
- cancel work,
- preserve non-enumerability and multi-tenant boundaries.

This surface must also tolerate MCP server restarts and new host sessions (session independence), per
ADR-0010.

## Decision

### 1) Tool surface and naming
Add a compat job tool surface for each long-running tool, plus common job management tools:
- `{tool_name}_submit(...) -> {job_id, ...}`
- `job_get(job_id) -> {state, progress, ...}`
- `job_result(job_id) -> {final_payload}`
- `job_cancel(job_id) -> {state}`
- optional `job_wait(job_id, max_wait_s, poll_interval_s)`

The final payload returned by `job_result` MUST match the existing tool payload schema for that tool
(same as `tasks/result` for SEP-1686).

### 2) `job_id` is a stable `gsd` job identifier (not a raw backend task key)
`job_id` MUST be:
- stable across MCP server restarts and host session changes,
- opaque (must not embed tenant/subject identity),
- non-guessable (sufficient entropy),
- usable to locate the underlying backend execution via a mapping record.

Rationale: this preserves flexibility to change backend task storage keys without breaking clients,
and it allows authorization checks and non-enumerable responses to be enforced at a stable boundary.

### 3) Job state model (external contract)
`job_get` exposes a stable state vocabulary:
- `queued`
- `running`
- `completed`
- `failed`
- `cancelled`

Additionally:
- `job_get` returns a best-effort `progress_message` snapshot and timestamps (`created_at`,
  `started_at`, `updated_at`, `finished_at` when known).
- `job_result` returns the final tool payload only when state is terminal (`completed`/`failed`/
  `cancelled`), otherwise a “not ready” response.

### 4) Progress and artifacts during execution
Minimum progress surface:
- a single “latest progress message” snapshot (portable across transports and backends).

Optional, session-scoped enhancements:
- if the job produces a browser `session_id`, `job_get` may return it so callers can use
  `get_run_events` / `get_screenshots` while the job is running.

If we want “check while running” UX to work reliably, pre-allocate and persist `session_id` at submit
time (instead of only after the worker starts).

### 5) Authorization and non-enumerability (compat jobs)
Authorization is identity-scoped (tenant + subject), not “who knows the `job_id`”.

For `job_get`/`job_result`/`job_cancel`:
- if the job does not exist OR the caller is not authorized, return a non-enumerable “not found”
  response (unless a deployment explicitly opts into `403` for observability).

## Consequences

### Positive
- Codex-compatible “submit + poll” UX without SEP-1686 support in the host.
- Stable client contract independent of backend task keying.
- Clear non-enumerability semantics for multi-tenant deployments.

### Negative / Costs
- Additional API surface to specify, implement, and test.
- Requires a durable mapping record (job_id -> backend execution key + ownership + metadata).

## Implementation Notes
- Persist a job ownership/mapping record containing:
  - `job_id`, `tool_name`, `tenant_id`, `subject_id`, `created_at`, `expires_at` (retention),
  - backend execution key (e.g., Docket task key) and any required lookup indirection,
  - optional `session_id` (pre-allocated at submit for “check while running”).
- Add conformance tests:
  - submit job, restart server, `job_get`/`job_result` still works (same identity)
  - cross-tenant/subject access is non-enumerable

## Open Questions
- Should `job_wait` be part of the stable surface, or kept as a client convenience?
- Should `job_get` expose structured progress (step counts) in addition to `progress_message`?
- Retention policy: how long after completion should `job_result` and artifacts remain available?
  Track in ADR-0017.

## References
- ADR-0010: Decouple execution from MCP server + add compat job tools
- ADR-0017: Job/task retention and cleanup policy
- `docs/planning/BACKLOG.md`
