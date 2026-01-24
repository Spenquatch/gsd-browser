# Decisions and spec gaps (FastMCP v2 Option B)

Last updated: 2026-01-24

This document tracks **remaining** decision points and spec gaps that are not fully pinned down yet,
even though the core Option B ADR set has largely been accepted.

If you resolve an item, update its status and add a short “Decision” section (or link to the ADR/PR
that records the decision).

## Index (open items)

| ID | Area | Status | Summary | Primary references |
|---:|------|--------|---------|--------------------|
| DR-0012-01 | SEP-1686 task lookup | **Resolved** | Fail-fast fallback if FastMCP task handlers cannot be overridden cleanly | `docs/adr/ADR-0012-session-independent-task-lookup-for-sep-1686.md` |
| DR-0013-01 | HTTP auth | **Resolved** | Protected Resource Metadata: single protected resource per deployment | `docs/adr/ADR-0013-mcp-compliant-http-authorization-surfaces-and-scope-model.md` |
| DR-0013-02 | HTTP auth | **Resolved** | JWT scope extraction: claim names, parsing rules, and mapping to required scopes | `docs/adr/ADR-0013-mcp-compliant-http-authorization-surfaces-and-scope-model.md`, `gsd-browser/docs/api/FAST_MCP_V2_CANONICAL_SPEC.md` |
| DR-0018-01 | 8081 management API | **Resolved** | Pin listing contract details: pagination/cursors, filters, sort, admin endpoints, error model | `docs/adr/ADR-0018-task-enumeration-surfaces-for-decoupled-operations.md`, `gsd-browser/docs/api/HTTP_API.md` |
| DR-SEC-01 | Identity + admin model | **Resolved** | Identity extraction + API key mapping + admin gating invariants across 8080/8081 | `docs/adr/ADR-0018-task-enumeration-surfaces-for-decoupled-operations.md`, `docs/adr/ADR-0013-mcp-compliant-http-authorization-surfaces-and-scope-model.md` |
| DR-0018-02 | 8081 management API | **Resolved** | API key configuration contract for 8081: file format, mapping to identity/scopes, and rotation | `gsd-browser/docs/api/HTTP_API.md`, `docs/adr/ADR-0018-task-enumeration-surfaces-for-decoupled-operations.md` |
| DR-RET-01 | Retention/maintenance | **Resolved** | Retention windows + env var naming: unify docs with canonical spec + current code defaults | `docs/adr/ADR-0015-option-b-operational-topology-and-reference-deployment.md`, `docs/adr/ADR-0017-job-task-retention-and-cleanup-policy.md`, `gsd-browser/docs/api/FAST_MCP_V2_CANONICAL_SPEC.md` |
| DR-WRAP-01 | Wrapper strategy | **Resolved** | MCP wrapper tools for ops surfaces: shared service layer (no loopback HTTP dependency) | `docs/adr/ADR-0018-task-enumeration-surfaces-for-decoupled-operations.md`, `gsd-browser/docs/api/HTTP_API.md` |
| DR-JOBS-01 | Compat jobs errors | **Resolved** | Standard timeout/error payloads for `job_wait` + shared management API error payloads | `docs/adr/ADR-0011-compat-job-tools-contract-and-job-id-strategy.md`, `gsd-browser/docs/api/HTTP_API.md` |

---

## DR-0012-01: Fallback strategy if FastMCP task handlers cannot be overridden cleanly

**Status:** Resolved (2026-01-24)

**Context**
- We currently support session-independent `tasks/get|result|cancel` by using persisted ownership
  records (ADR-0012).
- This relies on being able to hook/override (or otherwise route) FastMCP’s default task protocol
  handlers.
- If upstream changes break this approach, we need a clear fallback contract for “check later”.

**Decision needed**
- What is the supported fallback behavior if handler override becomes impractical?

**Options**
- **A. Keep SEP-1686 cross-session support as hard requirement**: pin FastMCP versions and/or carry a
  patch layer to keep handler override stable.
- **B. Document a limitation**: SEP-1686 “check later” becomes session-dependent; direct users to
  compat jobs (`*_submit` + `job_get`/`job_result`) for durable check-later workflows.
- **C. Implement an alternate task store lookup**: persist additional backend locator data so lookup
  does not depend on overriding FastMCP handlers.

**Follow-up tasks**
- Add a short conformance note to ADR-0012 once the fallback is chosen.
- Add an explicit test matrix (pin expected behavior per option).

**Decision (2026-01-24)**
- Choose **Option A**: SEP-1686 cross-session “check later” support remains a hard requirement for the
  Option B runtime.
- Fallback behavior is **fail-fast** (not silent degradation):
  - if `gsd` cannot install/override the task protocol handlers needed for session-independent lookup,
    the Option B runtime MUST refuse to start (or must explicitly disable v2 and surface a clear error).
  - this avoids “works sometimes” behavior and preserves the canonical spec guarantees.

---

## DR-0013-01: Protected Resource Metadata (RFC 9728) — multiple resources and final endpoint shape

**Status:** Resolved (2026-01-24)

**Context**
- ADR-0013 is accepted and defines path-aware metadata with base-path detection.
- The remaining ambiguity is whether we support multiple protected resources (and how clients discover
  which resource they’re calling) in complex proxy/hosting setups.

**Decision needed**
- Do we support multiple protected resources (and if so, how are they identified)?

**Options**
- **A. Single resource per server**: one metadata document per deployment (simplest).
- **B. Resource per base path**: metadata varies by `{base_path}` (common for reverse proxies).
- **C. Resource per host + base path**: metadata varies by host header + base path (more complex; useful
  for multi-tenant front doors).

**Follow-up tasks**
- Update ADR-0013 “Open Questions” when decided.
- Update test matrix to include the chosen multi-resource behavior.

**Decision (2026-01-24)**
- Choose **Option A**: **single protected resource per server deployment**.
- Path-aware hosting under a base path is supported (via `{base_path}/.well-known/...`), but the server
  does not attempt to present multiple distinct protected resources from a single running instance.

---

## DR-0018-01: 8081 management API contract details (pagination, filtering, admin gating, errors)

**Status:** Resolved (2026-01-24)

**Context**
- ADR-0018 defines the existence and purpose of 8081 but does not fully specify the *contract*.
- `gsd-browser/docs/api/HTTP_API.md` currently contains example shapes, not a pinned schema.

**Decision needed**
- Pin the stable contract for listing and inspection endpoints so CLI and operators can depend on it.

**Spec items to pin**
- Pagination: cursor format (opaque string), stability guarantees, and max limits.
- Sorting: default order (e.g., `created_at desc`), and whether the API supports alternate sorts.
- Filtering: supported query params (`status`, `since`, `tool_name`, etc.) and validation behavior.
- Admin gating: what flags/env vars/scopes enable admin (cross-identity) access.
- Error model: stable JSON error payload format + HTTP status usage with non-enumerability semantics.

**Follow-up tasks**
- Promote example payloads in `gsd-browser/docs/api/HTTP_API.md` to a pinned contract section.
- Add JSON schemas for 8081 responses if we want machine-checkable guarantees (optional).

**Decision (2026-01-24)**
- The 8081 API is pinned as a **minimal v1** contract:
  - Identity-scoped listing: `GET /api/v1/tasks`
  - Admin listing: `GET /api/v1/admin/tasks` (explicitly gated; see DR-SEC-01)
- Pagination uses an **opaque cursor** (`cursor` / `next_cursor`) that is bound to the query parameters.
- Sorting is fixed: **`created_at desc`** (no alternate sort in v1).
- Filtering is limited to a small, validated set (start narrow; expand later without breaking v1):
  - `status`, `tool_name`, `since`, `limit`, `cursor`
- A stable JSON error payload shape is pinned and reused across 8081 endpoints (see DR-JOBS-01).

---

## DR-SEC-01: Identity extraction + admin model (8080 MCP HTTP and 8081 management REST)

**Status:** Resolved (2026-01-24)

**Context**
- ADR-0018 requires consistent identity extraction across 8080 and 8081.
- ADR-0013 introduces scopes; ADR-0018 introduces admin gating.
- We still need an explicit mapping: claims → `{tenant_id, subject_id}` and API key → identity.

**Decision needed**
- Pin the exact identity extraction contract and admin gating rules.

**Spec items to pin**
- Required JWT claims (or mapping rules) for `tenant_id` and `subject_id`.
- API key identity mapping: where keys live, what identity they map to, and whether API keys can be
  admin-scoped.
- Admin gating: env var(s) + required scope (`gsd:admin`) + audit logging expectations.
- Non-enumerability policy: when we return 404 vs 403 vs 401 across 8080 and 8081.

**Decision (2026-01-24)**
- **Identity extraction**:
  - HTTP identity is derived from JWT claims using the canonical mapping in
    `gsd-browser/docs/api/FAST_MCP_V2_CANONICAL_SPEC.md` (§1).
  - `tenant_id` claim name: `GSD_JWT_TENANT_ID_CLAIM` (default `tenant_id`)
  - `subject_id` claim name: `GSD_JWT_SUBJECT_ID_CLAIM` (default `sub`)
- **API keys**:
  - 8081 MAY additionally support `X-API-Key` for ops automation.
  - API keys map to `{tenant_id, subject_id, scopes[]}` and MAY be admin-scoped.
  - Location/format for API keys MUST be explicitly configured (no implicit defaults).
- **Admin gating** (safe-by-default):
  - admin endpoints (e.g., `/api/v1/admin/*`) require BOTH:
    - explicit server enablement (e.g., `GSD_ADMIN_MODE=1`), AND
    - caller authorization (`gsd:admin` scope).
  - admin access MUST emit audit logs.
- **Non-enumerability**:
  - `401`: missing/invalid authentication
  - `403`: authenticated but insufficient scope OR admin endpoints disabled
  - `404`: “not found” semantics for non-admin callers when a resource exists but is not authorized

---

## DR-JOBS-01: Standardize compat job timeout/error payloads

**Status:** Resolved (2026-01-24)

**Context**
- ADR-0011 pins `job_wait` semantics, but we still need stable error payloads for:
  - `job_wait` timeout responses, and
  - 8081 management API errors (and ideally shared semantics with 8080 MCP HTTP error mapping).

**Decision needed**
- Define a minimal, stable error payload format and reuse it across surfaces where appropriate.

**Follow-up tasks**
- Add “timeout error” response example for `job_wait` in ADR-0011 (or in the tool contract doc when we
  get to payload shapes).
- Add an “Errors” section to `gsd-browser/docs/api/HTTP_API.md` with the pinned error JSON shape.

**Decision (2026-01-24)**
- **8081 REST error payload (pinned)**:
  - Responses use a stable JSON envelope:
    ```json
    {
      "error": {
        "code": "invalid_cursor",
        "message": "Cursor does not match query",
        "details": { "hint": "Do not reuse cursors across filters." }
      }
    }
    ```
- **Compat jobs tool errors (pinned direction)**:
  - `job_wait` timeout returns a stable timeout payload (`version`ed) that includes current job state
    and an `error` object with a stable `code` (e.g., `TIMEOUT`), rather than returning an ambiguous
    partial tool result.
  - Management API and compat job errors should share the same `{code,message,details}` convention.

---

## DR-0013-02: JWT scope extraction (claims → scopes) for 8080 (MCP HTTP) and 8081 (management REST)

**Status:** Resolved (2026-01-24)

**Context**
- ADR-0013 defines required scopes (`gsd:browser:execute`, `gsd:browser:read`, `gsd:admin`) and how
  `WWW-Authenticate` challenges should indicate insufficient scope.
- To implement this consistently across 8080 and 8081, we must pin:
  - which JWT claim(s) carry scopes,
  - how they are parsed (string vs list),
  - how missing/invalid scope claims behave.

**Decision needed**
- Pin the scope claim extraction contract (claim names + parsing rules) and the error semantics for
  “authenticated but insufficient scope”.

**Options**
- **A. Prefer `scope` (string) with fallback to `scp` (array|string)**:
  - `scope`: space-separated string (OAuth-ish)
  - `scp`: array of strings (common in some IdPs) or space-separated string
- **B. Single claim name only**:
  - Configurable claim name (no fallback); simplest but less compatible across IdPs
- **C. Provider-specific adapters**:
  - Multiple claim schemas by IdP type (more complexity; defer unless required)

**Recommended decision**
- Choose **Option A** for interoperability:
  - Default extraction order: `scope` then `scp`
  - Accept either:
    - `scope: "a b c"` (split on spaces), or
    - `scp: ["a","b","c"]`, or `scp: "a b c"`
  - Unknown/invalid claim format results in “no scopes” (treated as insufficient scope).

**Decision (2026-01-24)**
- Choose **Option A**.
- Scope extraction is pinned as:
  - Prefer JWT claim `scope` (string; space-separated), fallback to `scp` (array of strings or
    space-separated string).
  - Any invalid scope claim format results in “no scopes”.

**Follow-up tasks**
- Add a short “Scope claim extraction” section to ADR-0013 implementation notes (or canonical spec).
- Add conformance tests for 401/403 behavior across 8080 and 8081.

---

## DR-0018-02: API key configuration contract for 8081

**Status:** Resolved (2026-01-24)

**Context**
- ADR-0018 and the 8081 contract allow `X-API-Key` for ops automation.
- We must pin the operator configuration mechanism so it is safe-by-default and testable.

**Decision needed**
- Pin the API key source (env vs file), schema, and mapping to identity/scopes.

**Options**
- **A. File-based key registry (recommended)**:
  - `GSD_API_KEYS_FILE=/path/to/keys.json`
  - Each key maps to `{tenant_id, subject_id, scopes[]}`
- **B. Env-based JSON**:
  - `GSD_API_KEYS_JSON='[...]'` (harder to manage/rotate; leaks via env dumps)
- **C. External provider**:
  - Delegate to OIDC only; no API keys (simplest; less operator-friendly)

**Recommended decision**
- Choose **Option A**:
  - `GSD_API_KEYS_FILE` is required to enable API keys (no implicit defaults).
  - File contains a JSON array of entries:
    - `key` (string) OR `key_sha256` (string)
    - `tenant_id`, `subject_id`, `scopes` (string[])
    - optional `label` and `created_at` for audit
  - In production, prefer `key_sha256` entries to avoid storing plaintext keys on disk.

**Decision (2026-01-24)**
- Choose **Option A**.
- 8081 API keys are enabled only when `GSD_API_KEYS_FILE` is set.
- The key registry format is pinned (JSON array of entries mapping to identity + scopes), and
  production deployments should prefer `key_sha256` entries.

**Follow-up tasks**
- Document the exact JSON schema in `gsd-browser/docs/api/HTTP_API.md`.
- Add rotation guidance (reload-on-start initially; optional SIGHUP reload later).

---

## DR-RET-01: Retention windows + maintenance env var naming drift

**Status:** Resolved (2026-01-24)

**Context**
- The canonical spec and current implementation use:
  - `GSD_RETENTION_SECONDS_DEV|PROD` for retention defaults, and
  - `GSD_CLEANUP_INTERVAL_S` for cleanup interval scheduling/locking.
- ADR-0015 references `GSD_MAINTENANCE_INTERVAL`.
- ADR-0017 references `GSD_JOB_RETENTION_*` / `GSD_ARTIFACT_RETENTION_*` duration-style vars and
  defaults that do not match the current implementation.

**Decision needed**
- Pin the canonical env var names and default values so planning/tasks don’t encode conflicting
  requirements.

**Recommended decision**
- Treat `gsd-browser/docs/api/FAST_MCP_V2_CANONICAL_SPEC.md` as authoritative:
  - Use `GSD_CLEANUP_INTERVAL_S` (seconds; default `300`) everywhere.
  - Use `GSD_RETENTION_SECONDS_DEV` (default `86400`) and `GSD_RETENTION_SECONDS_PROD`
    (default `604800`) as the implemented retention window for Option B artifacts/index records.
  - Defer “separate job vs artifact retention” until compat jobs exist; when implemented, introduce
    new `*_SECONDS_*` variables (not duration strings) and update the canonical spec in the same PR.

**Decision (2026-01-24)**
- Adopt the canonical spec env vars everywhere:
  - `GSD_CLEANUP_INTERVAL_S` (default `300`)
  - `GSD_RETENTION_SECONDS_DEV` (default `86400`)
  - `GSD_RETENTION_SECONDS_PROD` (default `604800`)
- Remove/avoid the `GSD_MAINTENANCE_INTERVAL` name in docs.

**Follow-up tasks**
- Align ADR-0015 and ADR-0017 language to the canonical env vars and defaults.
- Remove/avoid the `GSD_MAINTENANCE_INTERVAL` name in docs to prevent operator confusion.

---

## DR-WRAP-01: MCP wrapper tools for ops surfaces (service layer vs calling 8081 over HTTP)

**Status:** Resolved (2026-01-24)

**Context**
- We plan to expose a REST API (8081) so that “ops” workflows exist even when MCP hosts lack SEP-1686.
- We also plan to expose MCP tools that wrap those ops surfaces so any MCP host can use them as
  regular tools.
- If wrapper tools call 8081 over HTTP, we introduce network/config failure modes even when running
  in-process.

**Decision needed**
- Pin the recommended implementation pattern for wrapper tools.

**Options**
- **A. Shared internal service layer (recommended)**:
  - Implement listing/inspection logic once (service functions).
  - 8081 REST endpoints and MCP wrapper tools both call the same service layer.
- **B. Wrapper tools call 8081 over HTTP**:
  - Simpler wiring, but adds failure modes and can complicate auth propagation.

**Recommended decision**
- Choose **Option A**: shared internal service layer.
  - Wrapper tools should not depend on an HTTP loopback call to function.
  - REST remains the canonical external interface; MCP tools are convenience wrappers over the same
    implementation, not a second source of truth.

**Decision (2026-01-24)**
- Choose **Option A**.
- Implement listing/inspection logic once as a shared internal service layer; both 8081 REST endpoints
  and MCP wrapper tools call into it. MCP wrappers must not depend on loopback HTTP calls.
