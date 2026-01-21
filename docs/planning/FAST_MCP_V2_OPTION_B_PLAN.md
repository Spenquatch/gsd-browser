# FastMCP v2 “Option B” (scale-ready) — Spec Checklist + Implementation Plan

This document is a continuation/handoff plan for migrating `gsd` to FastMCP v2 long-running tasks
(SEP-1686) and distributed artifact storage (S3 + Redis index), while preventing API/contract drift.

## Current branch / status
- Status: Option B core has landed; this document is now primarily historical context.
- What’s done:
  - ADRs exist and have concrete decisions recorded: `docs/adr/ADR-0008-*.md`, `docs/adr/ADR-0009-*.md`
  - Machine-checkable API contract exists:
    - Pydantic: `gsd-browser/src/gsd_browser/contracts/v1.py`
    - Exported JSON Schema (enforced by tests): `gsd-browser/docs/api/jsonschema/`
    - Export command: `gsd-browser/tools/export_contract_schemas.py`
  - Contract docs: `gsd-browser/docs/api/MCP_TOOLS.md`, `gsd-browser/docs/api/MCP_TASKS.md`
- What’s not done yet:
  - The legacy default runtime is still the official SDK `mcp.server.fastmcp` (FastMCP v2 is behind
    `GSD_USE_FASTMCP_V2=true`).
  - Codex-compatible “compat job tools” (submit/status/result/cancel) are not implemented yet; Codex does not
    currently implement SEP-1686 as an MCP host.
  - “Client-independent” long jobs (external workers as the default execution model) need packaging/docs and
    a supported worker entrypoint (server concurrency=0, separate workers>0).
  - MCP-compliant HTTP OAuth discovery/challenge surfaces (RFC 9728 `resource_metadata`, `WWW-Authenticate`
    semantics, step-up scopes) are not implemented yet (JWT verification is implemented).
  - Ensure “check later” lookups are independent of the current MCP session ID (identity-scoped access).

Notes:
- This document started as a migration checklist. Most implementation work has landed; remaining follow-ons are
  tracked in `docs/planning/BACKLOG.md` (and the canonical implemented-vs-planned view is
  `gsd-browser/docs/api/STATUS.md`).

## Locked decisions (already chosen)
From ADR-0008 / ADR-0009:
- Long tools are task-required: `web_eval_agent`, `web_task_agent`, `web_task_agent_github`.
- Task TTL defaults are server-defined; client TTL override allowed only behind an env toggle and within
  bounded min/max (reject out-of-range).
- `tasks/get|result|cancel` access is identity/tenant-scoped (not session-only).
- Artifact delivery is phased:
  - Phase 1: inline delivery via MCP payloads, but API includes presigned-url-ready fields.
  - Phase 1 still writes artifacts to S3-compatible storage + Redis index from day 1.
  - Phase 2: switch large/binary artifacts to presigned URLs without breaking schema.
- Retention defaults: dev ~24h, prod ~7d (overrideable).
- Multi-tenant boundaries: tenant-prefixed keys + TLS + SSE at rest baseline.
- SeaweedFS is the initial self-hosted S3 reference deployment; RustFS remains an alternative.

## Spec surfaces that must be fully specified before implementation
The following are “definition of done” specs required to avoid integration drift.

### S0: Migration truth / boundary (docs + code)
Goal: avoid confusion that tasks/FastMCP v2 are already implemented.
- Deliverables:
  - A short “status header” explicitly stating what is implemented vs planned:
    - `gsd-browser/docs/api/MCP_TASKS.md` (and optionally `gsd-browser/README.md`)
    - (Optional) `gsd-browser/docs/api/STATUS.md` as the canonical pointer.
  - A “minimum supported versions” statement for FastMCP v2 + Docket + Redis.
- Notes:
  - Keep this statement as the single source of truth; other docs should point to it.

### S1: Schema evolution policy (strict vs extensible)
Problem: current Pydantic/JSON Schema are strict (`extra="forbid"`, `additionalProperties=false`), but
docs previously implied additive evolution within a version.
- Decision required:
  - `Strict`: any new field => new `version` (`v2`), keep strict schemas.
  - `Extensible`: allow unknown keys at least at top-level, document “clients ignore unknowns”.
- Deliverables:
  - Update `gsd-browser/docs/api/MCP_TOOLS.md` versioning policy.
  - Ensure `gsd-browser/src/gsd_browser/contracts/v1.py` matches the policy.
  - Ensure the schema export + enforcement test align.

### S2: Error/diagnostic taxonomy (align ADR goals with contracts)
Problem: `errors_top[].type` currently only supports `"console"|"network"` but ADR goals include
agent/provider/validation failures.
- Decisions required:
  - Expand `errors_top` taxonomy (e.g., add `"agent"`, maybe `"provider"`, `"tool"`).
  - Add a stable machine-readable `code` field (recommended) separate from human `summary`.
  - Define how cancellations/timeouts appear (e.g., include a ranked failure).
- Deliverables:
  - Update `RankedFailureV1` in `gsd-browser/src/gsd_browser/contracts/v1.py`.
  - Update `rank_failures_for_session(...)` behavior and any event recording that feeds it.
  - Update docs + exported schemas + tests.

### S3: Identity/tenant binding invariants (tasks + artifacts)
Goal: make multi-tenant authZ enforceable and testable.
- Decisions required:
  - Define identity sources per transport:
    - `stdio`: typically single-tenant (local trust boundary); define “tenant_id=local” semantics.
    - `http`: JWT/OIDC/OAuth provider; define required claims (`tenant_id`, `subject_id`, etc.).
  - Define what is persisted:
    - Task record: `{tenant_id, subject_id, created_at, tool_name, session_id?}`
    - Artifact index record: `{tenant_id, session_id, artifact_key, created_at, ...}`
  - Define presigned URL policy:
    - TTL, GET-only, scope to tenant key prefix, generated only after authZ check.
- Deliverables:
  - Add an “AuthZ invariants” section to ADR-0008 and ADR-0009 (or a shared security ADR).
  - Define the interface between auth middleware and task/artifact layers.
  - Add unit tests for cross-tenant denial (task + artifact retrieval).

### S4: Artifact metadata contract (Phase 2 safe)
Goal: make Phase 2 presigned flip non-breaking and robust.
- Decisions required:
  - Define artifact reference shape beyond `{key,url}`:
    - recommend adding at least: `content_type`, `size_bytes`, `created_at`, `url_expires_at`
  - Disambiguate screenshot “page URL” vs artifact URL:
    - schema uses `url` today; decide if v1 stays as-is (document as page URL) or version bump to `page_url`.
  - Define mapping from `screenshots[]` header objects to inline `ImageContent` items:
    - ordering, or add `inline_image_id`/`screenshot_id` field.
- Deliverables:
  - Update `GetScreenshotsPayloadV1` schema and docs.
  - Export schemas, update enforcement tests.

### S5: FastMCP v2 task semantics (TTL, polling, progress)
Goal: define operational behavior so clients have a stable UX.
- Decisions required:
  - Server default TTL per tool (minutes) and min/max bounds.
  - Env toggle name(s) for allowing client TTL overrides.
  - Poll interval suggestion per tool (and how frequently we emit progress).
  - Progress “units” for agent loops (steps vs percent).
- Deliverables:
  - Document in `gsd-browser/docs/api/MCP_TASKS.md`.
  - Add conformance test plan (see below).

## S0–S5 resolution pointers (this branch)
- S0 (migration boundary): `gsd-browser/docs/api/STATUS.md`
- S1 (schema evolution policy): `gsd-browser/docs/api/MCP_TOOLS.md` (Versioning policy)
- S2 (diagnostics taxonomy): `gsd-browser/docs/api/MCP_TOOLS.md` (`errors_top`) + `gsd-browser/src/gsd_browser/contracts/v1.py`
- S3 (identity/tenant invariants): `docs/adr/ADR-0008-fastmcp-v2-redis-backed-long-running-tasks.md` and `docs/adr/ADR-0009-distributed-artifact-storage-for-scaled-tasks.md`
- S4 (artifact metadata for Phase 2): `gsd-browser/docs/api/MCP_TOOLS.md` (`get_screenshots`) + `gsd-browser/src/gsd_browser/contracts/v1.py`
- S5 (task semantics): `gsd-browser/docs/api/MCP_TASKS.md`
- Canonical implementation spec (no open questions): `gsd-browser/docs/api/FAST_MCP_V2_CANONICAL_SPEC.md`


## Implementation phases (once S0–S5 are complete)
### I1: Framework migration
- Swap server implementation from `mcp.server.fastmcp` to `jlowin/fastmcp` v2.
- Ensure tool registration + tool exposure policy still works.

### I2: Task execution end-to-end
- Configure long tools as task-required.
- Implement progress + cancellation cleanup paths.
- Implement identity/tenant storage for task ownership.

### I3: Distributed artifact store
- Implement `ArtifactStore` + Redis index (tenant-prefixed).
- Wire screenshots/run-events to write to the store and read from it.
- Keep Phase 1 inline responses compatible with current contract.

## Conformance / test gates
Before calling the migration “complete”, add at least:
- Task lifecycle E2E:
  - call tool (task mode) → receive Task → `tasks/get` transitions → `tasks/result` matches schema
- Cancellation E2E:
  - cancel task → status becomes cancelled → cleanup performed → result consistent
- Multi-tenant denial:
  - task/artifact created under tenant A cannot be fetched by tenant B
- Schema drift gate:
  - `export_contract_schemas.py` output must match committed JSON Schemas (already implemented)

## Reviewer notes captured (for continuity)
Third-party review raised (summarized):
- Migration truth is not explicit (docs vs code mismatch)
- Schema evolution policy contradicts strict schemas
- Error taxonomy too narrow for stated ADR goals
- Multi-tenant binding points underspecified
- Artifact metadata insufficient for a safe presigned flip
