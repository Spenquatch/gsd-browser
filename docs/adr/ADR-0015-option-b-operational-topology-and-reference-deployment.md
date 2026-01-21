# ADR-0015: Option B operational topology and reference deployment

## Status
Proposed

## Context
Option B (FastMCP v2 + Redis-backed tasks + distributed artifact storage) enables a scale-ready,
client-independent execution model, but it also introduces an operational topology that must be
documented and supported:
- server processes (HTTP/stdio) that accept MCP calls,
- a Redis/Valkey backend for task state (Docket),
- one or more worker processes that execute queued work,
- optional S3-compatible object storage for artifacts and a Redis index,
- optional maintenance work (pruning/cleanup).

Without a “blessed” reference topology and clear entrypoints, operators will assemble incompatible
shapes that break durability, identity boundaries, or cleanup.

## Decision

### 1) Supported deployment shapes
Define supported shapes explicitly:
- Local/dev:
  - embedded execution allowed (`FASTMCP_DOCKET_CONCURRENCY>0` in the server process), and/or
  - single-machine server + worker + redis via compose.
- Production:
  - server processes run with `FASTMCP_DOCKET_CONCURRENCY=0` (do not execute),
  - one or more external worker processes run with `FASTMCP_DOCKET_CONCURRENCY>0`,
  - all processes share the same Docket backend (`FASTMCP_DOCKET_URL`, `FASTMCP_DOCKET_NAME`),
  - artifacts are stored in shared storage if multiple replicas are used.

### 2) Maintenance responsibilities are explicit
Pick and document where maintenance runs (artifact cleanup/pruning/job retention enforcement):
- worker-led maintenance,
- server-led maintenance, or
- a dedicated maintenance process.

### 3) Provide versioned reference deployments
Provide a versioned, runnable reference deployment (compose) that includes:
- MCP server (HTTP),
- Redis/Valkey,
- worker(s),
- optional S3 gateway (e.g., SeaweedFS) if artifact persistence is enabled.

## Consequences

### Positive
- Operators have a known-good topology to copy.
- Scaling guidance becomes concrete (how to add workers; how to scale servers).

### Negative / Costs
- Requires ongoing maintenance of reference compose files and docs.

## Implementation Notes
- Document canonical CLI entrypoints for:
  - HTTP server (daemon-style),
  - worker process,
  - optional maintenance process.
- Document health checks and recommended scaling knobs (worker concurrency, queue depth metrics).

## Open Questions
- Which process should lead maintenance work in production?
- What are the “minimal required” components for a supported production deployment?

## References
- ADR-0010: Decouple execution from MCP server + add compat job tools
- ADR-0008: FastMCP v2 + Redis-backed MCP long-running tasks (SEP-1686)
- ADR-0009: Distributed artifact storage for scaled task execution
- `docs/planning/BACKLOG.md`

