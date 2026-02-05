# ADR-0015: Option B operational topology and reference deployment

## Status
Accepted

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
**Maintenance is worker-led** for simplicity and operational efficiency.

**Implementation:**
- One worker in the worker pool claims leadership via Redis-based distributed lock
- Leader worker runs cleanup loop on schedule (configurable interval)
- Maintenance tasks include:
  - Job/task retention enforcement (delete expired jobs per ADR-0017)
  - Artifact cleanup (screenshots, run-events)
  - Orphaned record pruning
- Leadership is re-acquired if the leader worker dies (another worker takes over)

**Configuration:**
- `GSD_CLEANUP_INTERVAL_S` - Cleanup interval in seconds (default: 300s / 5 minutes)

**Rationale:** Workers already connect to Redis/Docket and understand task lifecycle. One worker claims
leadership via distributed lock and runs cleanup. This is simpler than a dedicated maintenance process
while maintaining reliability through the worker pool. If all workers die, maintenance stops (acceptable
risk), but restarts when workers come back online.

### 3) Minimal production components
Define minimum viable production deployment for clarity and progressive complexity.

**Container architecture:**
- **gsd container** - MCP server and worker processes (can run both in single container or separate)
- **Docket + Redis container** - Combined Docket task queue and Redis backend
- **SeaweedFS container** - S3-compatible object storage (optional, for distributed artifacts)

**Minimal deployment (single-worker):**
- gsd container (server + worker)
- Docket + Redis container

**Characteristics:**
- Supports basic production workloads
- Single worker limits concurrency
- Artifacts stored locally within gsd container (not distributed)
- Cannot scale horizontally without artifact loss

**Production-ready deployment (multi-worker):**
- gsd container (server + worker pool)
- Docket + Redis container
- SeaweedFS container (S3-compatible storage)

**Characteristics:**
- True horizontal scaling capability
- Distributed artifact storage across workers
- No artifact locality concerns
- Production-grade from day one

**Rationale:** Define minimal as "gsd + Docket/Redis" for simplicity and fast onboarding. Document
SeaweedFS artifact storage as recommended for multi-worker deployments but not required for
single-worker scenarios. Progressive complexity allows operators to start simple and scale when needed.

**When to add SeaweedFS:**
- Multiple worker replicas (horizontal scaling)
- Worker node failures requiring artifact failover
- Long-term artifact retention requirements
- Compliance/audit requirements for artifact storage

### 4) Provide versioned reference deployments
Provide versioned, runnable reference deployments (docker-compose) for different scenarios:

**docker-compose.minimal.yml:**
- gsd container (server + worker)
- Docket + Redis container
- Health checks and restart policies
- Volume mounts for local artifacts

**docker-compose.production.yml:**
- gsd container (server + worker pool, scalable)
- Docket + Redis container
- SeaweedFS container (S3-compatible)
- Health checks and restart policies
- Distributed artifact storage configuration
- Recommended resource limits

**Versioning:**
- Reference deployments are versioned with gsd releases
- Breaking changes documented in deployment migration guides
- Backward compatibility maintained where possible

## Consequences

### Positive
- Operators have a known-good topology to copy.
- Scaling guidance becomes concrete (how to add workers; how to scale servers).

### Negative / Costs
- Requires ongoing maintenance of reference compose files and docs.

## Implementation Notes
### Worker-led maintenance implementation
- Implement maintenance loop in worker process with Redis-based leader election
- Use `GSD_CLEANUP_INTERVAL_S` environment variable (default: 300 seconds)
- Maintenance tasks:
  - Query expired jobs/tasks (based on retention windows from ADR-0017)
  - Delete job records and associated artifacts atomically
  - Log cleanup actions at INFO level (summary) and DEBUG level (per-job)
- Document maintenance responsibilities in operational runbook
- Add worker logs for maintenance actions (cleanup start/end, records pruned)

### Reference deployment creation
- Create `docker-compose.minimal.yml`:
  - gsd service (server + worker combined)
  - docket-redis service (combined Docket + Redis container)
  - Volume mounts for local artifact storage
  - Health check endpoints configured
  - Restart policies (unless-stopped)
- Create `docker-compose.production.yml`:
  - gsd service (scalable via replicas)
  - docket-redis service
  - seaweedfs service (S3-compatible storage)
  - Artifact storage configuration (S3 endpoints)
  - Resource limits and reservations
  - Health checks for all services
- Document artifact storage tradeoffs in deployment guide
- Add "When to add SeaweedFS" decision guide in deployment documentation

### CLI entrypoints documentation
- Document canonical CLI entrypoints:
  - `gsd mcp serve --http` - HTTP server (daemon-style)
  - `gsd worker` or similar - Worker process (to be defined)
  - Maintenance is automatic within workers (no separate process)
- Document health check endpoints:
  - `/health` - Server health
  - Worker health via Docket queue depth metrics
- Document recommended scaling knobs:
  - `FASTMCP_DOCKET_CONCURRENCY` - Worker task concurrency
  - Queue depth metrics for autoscaling decisions
  - Worker replica count for horizontal scaling

## Resolved Questions

### Maintenance Process Leadership
**Decision (2026-01-23):** Worker-led maintenance.

**Implementation:** Workers run cleanup loop on schedule using Redis-based leader election. One worker
claims leadership via distributed lock and runs cleanup. If leader dies, another worker takes over.

**Rationale:** Workers already connect to Redis/Docket and understand task lifecycle. One worker claims
leadership via distributed lock and runs cleanup. Simpler than dedicated maintenance process while
maintaining reliability through worker pool.

### Minimal Production Components
**Decision (2026-01-23):** Minimal deployment is gsd + Docket/Redis containers.

**Container architecture:**
- Minimal: gsd container + Docket/Redis container (combined)
- Production-ready: add SeaweedFS container (S3-compatible storage)

**Rationale:** Define minimal as "gsd + Docket/Redis" for simplicity. Document SeaweedFS artifact storage
as recommended for multi-worker deployments but not required for single-worker scenarios. Progressive
complexity allows operators to start simple and scale when needed.

## References
- ADR-0010: Decouple execution from MCP server + add compat job tools
- ADR-0008: FastMCP v2 + Redis-backed MCP long-running tasks (SEP-1686)
- ADR-0009: Distributed artifact storage for scaled task execution
- `docs/planning/BACKLOG.md`
