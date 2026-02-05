# ADR-0017: Job/task retention and cleanup policy

## Status
Accepted

## Context
Option B introduces multiple time horizons that affect user experience and operational cost:
- SEP-1686 task TTL / backend retention (Docket/task store),
- compat job retention (how long `job_get` / `job_result` remain available after completion),
- artifact retention (how long screenshots/run-events remain retrievable).

If these clocks are not defined explicitly, we risk:
- “check later” workflows failing unexpectedly (results expire too soon), or
- unbounded retention and storage growth.

This policy also interacts with operational topology (ADR-0015): in a multi-process world, some
process must periodically enforce cleanup/pruning.

## Decision

### 1) Treat task TTL as an execution backend concern
SEP-1686 task TTL governs backend task state retention and is tuned for execution/runtime behavior.
It is not, by itself, the product-level “how long users can fetch results”.

### 2) Define explicit retention windows (separate contracts)
Define and document retention windows for compat jobs and artifacts with environment-specific
defaults.

**Implemented retention window (Option B today):**
The current Option B implementation uses a single, environment-specific retention window for the
artifact index (Redis) and associated object-store artifacts (S3-compatible). This is controlled by
the canonical spec env vars:
- Development: `GSD_RETENTION_SECONDS_DEV=86400` (24 hours)
- Production: `GSD_RETENTION_SECONDS_PROD=604800` (7 days)

These names and defaults are authoritative in
`gsd-browser/docs/api/FAST_MCP_V2_CANONICAL_SPEC.md` (§8.7) and in the current implementation.

**Planned (future; compat jobs):**
When compat jobs are implemented (ADR-0011), we may introduce distinct job vs artifact retention
windows. If we do, the env var names and defaults must be pinned in the canonical spec in the same
change set (avoid drift).

**Retention and cleanup relationship (job vs artifacts):**
- Today (Option B as implemented), retention is a single window applied to artifacts/index records.
- In the future (once compat jobs exist), we may introduce separate job vs artifact windows:
  - Artifact retention may be shorter than job retention (to control storage).
  - When a job expires, any remaining associated artifacts should be deleted as part of the same
    cleanup operation (no long-lived orphans).
  - Deployments that require artifacts to remain available for the full job retention window must set
    artifact retention >= job retention (once separate knobs exist).

**Rationale for long retention:**
- "Check later" is a core value proposition for Option B (decoupled execution)
- Users expect results to be available across sessions, even with delays
- Storage is cheap relative to user frustration from expired results
- 24h/7d split balances UX reliability with storage costs

**Rationale for coupled cleanup:**
- Simplicity: predictable cleanup lifecycle and no long-lived orphan handling
- Artifacts without job context are useless to users
- Jobs without artifacts frustrate users (references to deleted data)
- Delete atomically when job expires
- Storage optimization via compression instead of independent retention

**Configuration:**
Retention windows are configurable via environment variables to allow operators to tune based on
storage/cost constraints. Defaults optimize for reliability and user experience.

### 3) Expiry behavior is non-enumerable by default
After expiry:
- treat the job/task as “not found” (non-enumerable) for callers without explicit operator/debug
  configuration.

This preserves security semantics consistent with task ownership enforcement and compat jobs
non-enumerability.

### 4) Cleanup leadership is explicit and coordinated
Cleanup/pruning MUST be performed by exactly one leader at a time in a shared backend, coordinated
via a distributed lock (e.g., Redis). The chosen leader process type is defined in ADR-0015.

### 5) Cleanup metrics and logging for operational visibility
Provide comprehensive observability for cleanup operations to enable production monitoring and
troubleshooting.

**Prometheus metrics:**
- `gsd_cleanup_jobs_pruned_total` - Counter of jobs deleted by cleanup
- `gsd_cleanup_duration_seconds` - Histogram of cleanup operation duration
- `gsd_cleanup_errors_total` - Counter of cleanup failures

**Structured logging:**
- **INFO level (summary):** Cleanup start/end with total counts
  - Example: "Cleanup completed: 42 jobs pruned, 156 artifacts deleted, duration=2.3s"
- **DEBUG level (per-job):** Individual job deletion details
  - Example: "Pruned job job_abc123: created=2026-01-20T10:00:00Z, expired=2026-01-21T10:00:00Z, artifacts=4"

**Rationale:**
Cleanup is critical infrastructure for production deployments. Operators must monitor success/failure
rates and diagnose issues when cleanup fails. Metrics enable alerting (e.g., cleanup_errors_total > 0),
while debug logs enable troubleshooting specific job retention issues. Metrics are cheap to emit;
outages from silent cleanup failures are expensive.
## Consequences

### Positive
- Predictable “check later” UX for clients (Codex/hosts).
- Bounded storage growth with clear operator expectations.
- Cleaner separation between backend TTL and product retention.

### Negative / Costs
- Requires additional metadata and a maintenance loop to enforce retention.
- Requires careful coordination to avoid concurrent cleanup races.

## Implementation Notes
### Retention window implementation
Implemented today:
- `GSD_RETENTION_SECONDS_DEV` (default: `86400`)
- `GSD_RETENTION_SECONDS_PROD` (default: `604800`)

Any future job-vs-artifact split must be introduced with explicit `*_SECONDS_*` variables and must
update the canonical spec in the same PR.

### Coupled retention implementation
Cleanup has two responsibilities:

Implemented today:
1) **Artifact pruning** (single retention window):
- Delete artifacts/index records whose retention window has elapsed.

Planned (future; compat jobs):
2) **Job expiry pruning** (job retention window):
- Cleanup loop deletes job + any remaining artifacts together when the job expires:
  1. Query expired jobs (`expires_at < now()`).
  2. For each expired job:
     - Delete job ownership record.
     - Delete any remaining artifact index entries.
     - Delete any remaining object store blobs (S3) by key prefix.
  3. Commit deletions atomically where possible.

### Cleanup metrics implementation
- Add Prometheus metric exports to cleanup loop:
  - `gsd_cleanup_jobs_pruned_total`: increment per job deleted
  - `gsd_cleanup_duration_seconds`: record total cleanup duration
  - `gsd_cleanup_errors_total`: increment on any cleanup error
- Structured logging:
  - INFO: log cleanup summary (total jobs/artifacts, duration)
  - DEBUG: log per-job deletion details (job_id, created_at, expires_at, artifact_count)
- Document metrics in an operational runbook.
- Add Grafana dashboard examples for cleanup monitoring:
  - cleanup rate over time
  - cleanup duration trends
  - error rate alerts

### Testing and verification
- Expired records return non-enumerable "not found".
- Cleanup deletes artifacts/index entries as expected.
- Job expiry pruning deletes the job record and any remaining artifacts.
- Artifact pruning respects the artifact retention window (artifacts can expire before the job does).
- Metrics are correctly emitted during cleanup.
- Logs include both summary and per-job details.
- Retention windows are configurable and respected.

## Resolved Questions

### Default Retention Windows
**Decision (2026-01-23):** Long retention optimized for "check later" UX.

**Implementation:**
- Development: `GSD_RETENTION_SECONDS_DEV=86400` (24h)
- Production: `GSD_RETENTION_SECONDS_PROD=604800` (7d)
- Configurable via environment variables

**Rationale:** "Check later" is a core value proposition for Option B. Users expect results to be
available across sessions. Storage is cheap; frustration from expired results is expensive. The
24h/7d split balances reliability with storage costs while supporting async workflows.

### Artifact vs Job Retention Independence
**Decision (2026-01-23):** Separate retention windows, coupled cleanup on job expiry.

**Implementation:**
- Separate job vs artifact retention windows are a planned follow-on once compat jobs exist.
- When the job expires, cleanup deletes the job record and any remaining artifacts together.
- Deployments that require full “job + artifacts” availability for the job retention window must set
  artifact retention >= job retention.

**Rationale:** This keeps operator control over storage (artifacts can be shorter-lived), while still
ensuring job expiry does not leave long-lived orphan artifacts behind.

### Cleanup Metrics and Logging
**Decision (2026-01-23):** Structured metrics + detailed debug logs.

**Implementation:**
- Prometheus metrics: `gsd_cleanup_jobs_pruned_total`, `gsd_cleanup_duration_seconds`, `gsd_cleanup_errors_total`
- Structured logging: INFO (summary), DEBUG (per-job details)
- Operational runbook documentation
- Grafana dashboard examples

**Rationale:** Cleanup is critical infrastructure. Operators must monitor success/failure rates and
diagnose issues. Metrics enable alerting and trend analysis. Debug logs enable troubleshooting
specific retention issues. Metrics are cheap; outages from silent cleanup failures are expensive.

## References
- ADR-0010: Decouple execution from MCP server + add compat job tools
- ADR-0011: Compat job tools contract and job ID strategy
- ADR-0015: Option B operational topology and reference deployment
- ADR-0009: Distributed artifact storage for scaled task execution
- `docs/planning/BACKLOG.md`
