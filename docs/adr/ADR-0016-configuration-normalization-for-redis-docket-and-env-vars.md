# ADR-0016: Configuration normalization for Redis/Docket and related env vars

## Status
Accepted

## Context
Option B relies on a Redis/Valkey backend for long-running task execution (Docket). There was drift
between:
- what the runtime actually reads (FastMCP/Docket variables like `FASTMCP_DOCKET_URL`), and
- what some docs/specs referenced (e.g., `GSD_REDIS_URL`).

This drift created operator confusion and made reference deployments harder to standardize.

## Decision

### 1) Single-Redis model via Docket
All Redis usage (task ownership, artifact indexing, maintenance locks) uses the Docket Redis backend
configured by `FASTMCP_DOCKET_URL`. There is no separate Redis instance for gsd-specific concerns.

### 2) Canonical env vars for Docket/Redis
The canonical configuration for the Docket backend is:
- `FASTMCP_DOCKET_URL` (required; must be `redis://...`)
- `FASTMCP_DOCKET_NAME`
- `FASTMCP_DOCKET_CONCURRENCY`

Docs and examples MUST treat these as the only knobs for Option B Redis configuration.

### 3) Remove `GSD_REDIS_URL` from the spec
`GSD_REDIS_URL` is NOT supported and MUST NOT appear in canonical documentation as a configuration
option. The code never reads it, and documenting it would mislead operators into thinking they need
to configure two Redis URLs.

Rationale: supporting an alias adds complexity (precedence rules, deprecation warnings, migration
docs) without meaningful benefit. A single, well-documented env var is simpler for operators.

## Consequences

### Positive
- Eliminates ambiguity for operators: one Redis URL (`FASTMCP_DOCKET_URL`), one backend.
- Makes compose examples and deployment docs consistent.
- Reduces code complexity (no alias parsing, no precedence logic).

### Negative / Costs
- None. `GSD_REDIS_URL` was never wired in the implementation, so no existing deployments rely on it.

## Implementation Notes
- Canonical spec §8.4 updated to explicitly state all Redis usage goes through `FASTMCP_DOCKET_URL`.
- No alias support; no migration path needed (the variable was documentation-only).

## Resolved Questions
- **Do we ever need separate Redis backends for different concerns?** No. The single Docket Redis
  instance handles task queuing, task ownership records, artifact index sorted sets, and maintenance
  locks. This simplifies deployment and reduces operational burden.
- **Is there a deprecation timeline for `GSD_REDIS_URL`?** Not applicable; it was never implemented.

## References
- ADR-0010: Decouple execution from MCP server + add compat job tools
- `docs/planning/BACKLOG.md`
- `gsd-browser/docs/api/FAST_MCP_V2_CANONICAL_SPEC.md` §8.4

