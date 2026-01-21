# ADR-0017: Job/task retention and cleanup policy

## Status
Proposed

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
Define and document separate retention windows for:
- compat jobs (`job_get` / `job_result` availability after completion), and
- artifacts (screenshots/run-events) referenced by session/job.

Retention windows may differ by deployment environment (`dev` vs `prod`) and must be bounded.

### 3) Expiry behavior is non-enumerable by default
After expiry:
- treat the job/task as “not found” (non-enumerable) for callers without explicit operator/debug
  configuration.

This preserves security semantics consistent with task ownership enforcement and compat jobs
non-enumerability.

### 4) Cleanup leadership is explicit and coordinated
Cleanup/pruning MUST be performed by exactly one leader at a time in a shared backend, coordinated
via a distributed lock (e.g., Redis). The chosen leader process type is defined in ADR-0015.

## Consequences

### Positive
- Predictable “check later” UX for clients (Codex/hosts).
- Bounded storage growth with clear operator expectations.
- Cleaner separation between backend TTL and product retention.

### Negative / Costs
- Requires additional metadata and a maintenance loop to enforce retention.
- Requires careful coordination to avoid concurrent cleanup races.

## Implementation Notes
- Record timestamps and expiry in ownership/mapping records (tasks + compat jobs) so cleanup is
  deterministic.
- Ensure cleanup can safely delete:
  - job/task ownership records,
  - artifact index entries,
  - object store blobs (S3) by key prefix.
- Add tests/verification steps:
  - expired records return non-enumerable “not found”
  - cleanup deletes artifacts/index entries as expected

## Open Questions
- Default retention windows for compat jobs vs artifacts (dev vs prod).
- Whether artifact retention is tied to job retention or can be longer (e.g., for audit/debug).
- Exact metrics/logging expected from the cleanup loop (for operators).

## References
- ADR-0010: Decouple execution from MCP server + add compat job tools
- ADR-0011: Compat job tools contract and job ID strategy
- ADR-0015: Option B operational topology and reference deployment
- ADR-0009: Distributed artifact storage for scaled task execution
- `docs/planning/BACKLOG.md`

