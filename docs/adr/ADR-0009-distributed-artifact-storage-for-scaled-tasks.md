# ADR-0009: Distributed artifact storage for scaled task execution

## Status
Proposed

## Context
“Option B” (scale-ready) implies that long-running browser/agent work can execute in separate worker
processes and/or across multiple machines. In that world, process-local state is not reliable:

- Screenshots captured by a worker may not be on the filesystem of the process serving MCP requests.
- Run events (console/network/agent step logs) generated during a task may not be accessible to
  another replica.
- The operator dashboard should be able to show artifacts regardless of where execution occurred.

Today, `gsd` collects artifacts in a runtime-managed, in-process shape and exposes retrieval via MCP
tools like `get_screenshots` and `get_run_events`. To avoid a later “scale refactor”, artifact
collection and retrieval must be designed for distributed execution now.

## Decision
1) Introduce an explicit artifact storage layer with a stable addressing scheme.

2) Store artifacts in shared storage that works across processes and machines:
- Primary: S3-compatible object storage.
  - Cloud: AWS S3 (or equivalent managed S3-compatible service).
  - Self-host: compare SeaweedFS vs RustFS (below) and pick a reference deployment.
- Development fallback: local filesystem artifact store (single-node convenience).

3) Make tool results reference artifacts by stable IDs/keys, not by in-memory objects:
- Long-running tools return a `session_id` and a compact summary, plus references (keys) to artifacts.
- Retrieval tools (`get_screenshots`, `get_run_events`) fetch from the artifact store by session ID
  and filters, so any server replica can serve the data.

4) Persist minimal metadata required for listing/filtering:
- Store indices/metadata in Redis (or another shared store) to support queries like “last N screenshots
  for session X” without scanning the entire object store.

5) Artifact delivery mode (phased):
- Phase 1 (default): return artifacts inline in MCP payloads for compatibility, but always include
  stable artifact references (`artifact_key` / `artifact_id`) and “presigned-url-ready” fields in the
  API schema (for example `url: null` initially).
- Phase 1 storage: still write artifacts to S3-compatible storage from day 1 (and index in Redis),
  so distributed execution works immediately even if retrieval is inline.
- Phase 2 (later): switch large/binary artifact delivery to pre-signed URLs without breaking
  clients (they already understand the URL fields).
- Control via env/config (example): `GSD_ARTIFACT_DELIVERY_MODE=inline|presigned|both`.

## Consequences
### Positive
- No “later refactor” to support separate workers or multiple replicas.
- Any replica can serve artifact retrieval requests.
- Artifacts can outlive the process that created them (aligned with task TTL/retention).

### Negative / Costs
- Adds storage dependencies and configuration (S3 + Redis).
- Requires careful attention to retention, privacy, and access control (artifacts may contain PII).
- Adds complexity to local development unless defaults are smooth.

## Implementation Notes
- Define an `ArtifactStore` interface (put/get/list/delete) and a small metadata/index layer.
- Establish deterministic object keys, for example:
  - `sessions/{session_id}/screenshots/{ts}-{step}-{type}.png`
  - `sessions/{session_id}/run-events/{ts}.jsonl`
- Keep binary payloads (images) out of Redis; store references + metadata only.
- Make the operator dashboard read from the same artifact store/index so it remains accurate under
  distributed execution.
- Self-hosted S3 comparison (SeaweedFS vs RustFS):
  - We must only depend on “common S3” behavior (PUT/GET/LIST, multipart uploads, auth, presigned
    URLs if used) so switching S3 providers remains an ops decision, not an app refactor.
  - Quick comparison (initial; validate before committing to prod):

    | Area | SeaweedFS | RustFS | Notes |
    | --- | --- | --- | --- |
    | Architecture | distributed (master/volume; optional filer + S3 gateway) | S3 object store service (advertises distributed + erasure-coded storage) | choose based on ops fit |
    | Ops footprint | more moving parts if using filer + gateway | potentially simpler service surface | validate HA story either way |
    | Metadata/index | filer can use pluggable metadata stores | unknown for our needs (validate listing semantics + metadata behavior) | we still keep our own Redis index |
    | Maturity/compat | needs validation against our required S3 behaviors | needs validation against our required S3 behaviors | run the same smoke matrix |

  - Evaluation criteria:
    - Deployment mode: single-node dev, multi-node cluster, upgrades/rollbacks
    - Data protection: replication vs erasure coding, failure domains, rebuild behavior
    - S3 API surface: multipart, ranged GET, ETags, listing semantics, bucket policies (if needed)
    - AuthN/AuthZ: access keys, policies, TLS termination options
    - Observability: metrics/logging, admin tooling, operational docs
    - Maturity signals: CI/compat testing, release cadence, upgrade notes, community adoption
  - SeaweedFS notes:
    - S3 API is provided via an S3 gateway, often paired with the optional “Filer” component.
    - Architecture is explicitly distributed (master/volume/filer); metadata backends are pluggable.
  - RustFS notes:
    - S3 server implemented in Rust; advertises distributed mode and erasure-coded storage.
    - Treat as “needs validation” for our exact required S3 semantics and ops maturity.
- Add configuration in `Settings` for:
  - backend selection (`fs` vs `s3`)
  - bucket/prefix, endpoint, region, auth mechanism
  - retention/cleanup policy aligned with task TTL

## Open Questions
- Should artifact retrieval use pre-signed URLs (for large blobs) vs MCP tool payloads?
- What is the right default retention policy in development vs production?
- Do we need per-tenant namespace separation and encryption-at-rest requirements?
- Which self-hosted S3 provider is the initial reference deployment (SeaweedFS or RustFS), and what
  is the minimal “smoke matrix” to validate compatibility?

## References
- ADR-0003: CDP-first browser-use integration (artifact expectations)
- ADR-0005: Browser-use contract alignment + artifact reliability
- ADR-0008: FastMCP v2 + Redis-backed MCP long-running tasks (SEP-1686)
