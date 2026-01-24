# ADR-0011: Compat job tools contract and job ID strategy

## Status
Accepted

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
- `job_get(job_id) -> {state, progress, progress_message, ...}`
- `job_result(job_id) -> {final_payload}`
- `job_cancel(job_id) -> {state}`
- `job_wait(job_id, max_wait_s, poll_interval_s) -> {final_payload}`

The final payload returned by `job_result` and `job_wait` MUST match the existing tool payload schema
for that tool (same as `tasks/result` for SEP-1686).

#### job_wait specification
`job_wait` is a stable API surface providing transitional compatibility for clients without SEP-1686
support. It enables synchronous "submit → wait → proceed" workflows during the multi-year client
adoption period.

Signature:
```python
job_wait(
    job_id: str,                    # required - job identifier to wait for
    max_wait_s: int = 300,          # optional - maximum wait time in seconds (default: 300)
    poll_interval_s: float = 2.0    # optional - internal polling interval (default: 2.0)
) -> dict
```

Parameters:
- **job_id**: The job identifier returned by `{tool_name}_submit`
- **max_wait_s**: Maximum time to wait before timeout (default: 300 seconds / 5 minutes)
  - Clients can override based on expected job duration
  - Capped at 3600 seconds (1 hour) to prevent infinite hangs and transport timeouts
  - Examples: quick tasks use 60s, complex workflows use 600s, research tasks use 1800s
- **poll_interval_s**: How often to check job status internally (default: 2 seconds)
  - Clients can override based on responsiveness needs
  - Minimum: 0.5 seconds to prevent server hammering
  - Examples: responsive UI uses 1s, background jobs use 5s

Behavior:
- Blocks the response until job completes or timeout occurs
- Returns job result (same schema as `job_result`) when job completes successfully
- Returns timeout error with current job status if `max_wait_s` is exceeded
- A timeout does **not** cancel the job; clients can continue to poll (`job_get`) and fetch later (`job_result`)
- Implemented as internal poll loop (client makes single synchronous tool call)
- Compatible with all MCP clients (no SEP-1686 support required)

Lifecycle:
- Maintained as stable API throughout SEP-1686 transition period (multi-year commitment)
- May be deprecated once SEP-1686 adoption reaches critical mass (with 12-month notice)
- Clients with SEP-1686 support should use native tasks instead

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
#### Progress reporting
`job_get` returns both freeform and structured progress information:

**progress_message** (string, always present):
- Human-readable progress description
- Portable across all tool types and backends
- Example: "Completed step 5 of 25: Navigating to login page"

**progress** (object, optional):
- Structured, machine-parseable progress data
- Fields:
  - `current` (int): Current step/iteration number
  - `total` (int): Total steps/iterations expected
  - `percentage` (float): Completion percentage (0.0 to 100.0)
- May be `null` for tools without clear step counts or before execution starts
- Example: `{"current": 5, "total": 25, "percentage": 20.0}`

Rationale: Browser automation inherently has step counts (agent iterations). Structured progress
enables client progress bars and UX while maintaining compatibility with simpler tools via the
optional nature of the field.

#### Session-scoped enhancements
Optional, session-scoped artifact access:
- If the job produces a browser `session_id`, `job_get` may return it so callers can use
  `get_run_events` / `get_screenshots` while the job is running.

For reliable "check while running" UX, pre-allocate and persist `session_id` at submit time
(instead of only after the worker starts).

### 5) Authorization and non-enumerability (compat jobs)
Authorization is identity-scoped (tenant + subject), not “who knows the `job_id`”.

For `job_get`/`job_result`/`job_cancel`:
- if the job does not exist OR the caller is not authorized, return a non-enumerable “not found”
  response (unless a deployment explicitly opts into `403` for observability).

## Consequences

### Positive
- Codex-compatible "submit + poll" UX without SEP-1686 support in the host
- `job_wait` enables synchronous workflows for non-SEP-1686 clients without custom polling logic
- Structured progress enables rich client UX (progress bars) while maintaining simple tool compatibility
- Stable client contract independent of backend task keying
- Clear non-enumerability semantics for multi-tenant deployments
- Immediate compatibility with all existing MCP clients regardless of SEP-1686 support
- Smooth transition path: clients can migrate to SEP-1686 when ready

### Negative / Costs
- Additional API surface to specify, implement, and test
- Requires a durable mapping record (job_id -> backend execution key + ownership + metadata)
- `job_wait` blocking calls may cause transport-level timeouts for very long jobs (mitigated by configurable `max_wait_s`)
- Maintenance burden for transitional tooling during multi-year SEP-1686 adoption period
- Structured progress adds payload size and requires step tracking in tool implementations

## Implementation Notes
### Job ownership/mapping record
Persist a job ownership/mapping record containing:
- `job_id`, `tool_name`, `tenant_id`, `subject_id`, `created_at`, `expires_at` (retention),
- backend execution key (e.g., Docket task key) and any required lookup indirection,
- optional `session_id` (pre-allocated at submit for "check while running").

### job_wait implementation
- Implement as internal poll loop with configurable timeout and interval
- Validate `max_wait_s` against cap (3600s) and reject if exceeded
- Validate `poll_interval_s` against minimum (0.5s) and reject if too low
- Poll `job_get` internally at specified interval
- Return job result payload (same schema as `job_result`) when job reaches terminal state
- Return timeout error with current job status if `max_wait_s` exceeded before completion
- Log timeout events for monitoring

### Structured progress implementation
- Update `web_eval_agent` job execution to populate structured progress from agent step counts
- `job_get` response includes:
  - `progress_message`: always present (string)
  - `progress`: optional object with `current`, `total`, `percentage` fields
  - `progress` may be `null` before execution starts or for tools without step tracking
- Calculate percentage as: `(current / total) * 100.0` when both values are known

### Conformance tests
- Submit job, restart server, `job_get`/`job_result` still works (same identity)
- Cross-tenant/subject access is non-enumerable
- `job_wait` timeout behavior: verify timeout error when job exceeds `max_wait_s`
- `job_wait` success behavior: verify returns result when job completes within timeout
- Structured progress: verify presence in `job_get` for web_eval_agent, verify optional for other tools
- Parameter validation: verify `max_wait_s` cap and `poll_interval_s` minimum enforcement

## Resolved Questions

### job_wait stable surface inclusion
**Decision (2026-01-22):** `job_wait` is part of the stable compat jobs API surface.

**Rationale:** MCP servers support SEP-1686 but most clients do not yet. Clients without SEP-1686
support are stuck in synchronous "call tool → wait → proceed" workflows. Many workflows require
blocking on job results before proceeding (data dependencies). `job_wait` provides the critical
bridge during the multi-year client adoption period. Without it, non-SEP-1686 clients cannot easily
use long-running jobs, defeating the purpose of compat job tools.

**Lifecycle:** Maintained as stable throughout the transition period with explicit deprecation notice
(12 months minimum) once SEP-1686 adoption reaches critical mass.

### Structured progress in job_get
**Decision (2026-01-22):** Add optional structured progress fields alongside `progress_message`.

**Rationale:** Browser automation inherently has step counts from agent iterations. Optional structured
fields (`current`, `total`, `percentage`) enable better client UX (progress bars) while maintaining
flexibility for tools without clear progress metrics. The optional nature ensures backward compatibility
and no schema burden for simple tools.

**Implementation:** See section 4 (Progress and artifacts during execution) for field specifications.

### Retention policy
**Decision:** Tracked in ADR-0017 (Job/task retention and cleanup policy).

Default retention windows:
- Development: jobs 24h, artifacts 12h
- Production: jobs 7d, artifacts 3d
- Artifacts may be pruned earlier per the artifact retention window; job expiry prunes any remaining artifacts (ADR-0017).

## References
- ADR-0010: Decouple execution from MCP server + add compat job tools
- ADR-0017: Job/task retention and cleanup policy
- `docs/planning/BACKLOG.md`
