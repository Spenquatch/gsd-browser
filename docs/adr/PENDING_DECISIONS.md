# Pending decisions / spec gaps (FastMCP v2 Option B)

Last updated: 2026-01-24

This document tracks **remaining** decision points and spec gaps that are not fully pinned down yet,
even though the core Option B ADR set has largely been accepted.

If you resolve an item, update its status and add a short “Decision” section (or link to the ADR/PR
that records the decision).

## Index (open items)

| ID | Area | Status | Summary | Primary references |
|---:|------|--------|---------|--------------------|
| DR-0012-01 | SEP-1686 task lookup | Open | Fallback if FastMCP task handlers cannot be overridden cleanly | `docs/adr/ADR-0012-session-independent-task-lookup-for-sep-1686.md` |
| DR-0013-01 | HTTP auth | Open | Protected Resource Metadata: multiple resources and final endpoint shape | `docs/adr/ADR-0013-mcp-compliant-http-authorization-surfaces-and-scope-model.md` |
| DR-0018-01 | 8081 management API | Open | Listing contract details: pagination/cursors, filters, sort, admin gating, error model | `docs/adr/ADR-0018-task-enumeration-surfaces-for-decoupled-operations.md`, `gsd-browser/docs/api/HTTP_API.md` |
| DR-SEC-01 | Identity + admin model | Open | Exact identity extraction + API key mapping + admin gating invariants across 8080/8081 | `docs/adr/ADR-0018-task-enumeration-surfaces-for-decoupled-operations.md`, `docs/adr/ADR-0013-mcp-compliant-http-authorization-surfaces-and-scope-model.md` |
| DR-JOBS-01 | Compat jobs errors | Open | Standard timeout/error payloads for `job_wait` + management API error payloads | `docs/adr/ADR-0011-compat-job-tools-contract-and-job-id-strategy.md`, `gsd-browser/docs/api/HTTP_API.md` |

---

## DR-0012-01: Fallback strategy if FastMCP task handlers cannot be overridden cleanly

**Status:** Open

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

---

## DR-0013-01: Protected Resource Metadata (RFC 9728) — multiple resources and final endpoint shape

**Status:** Open

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

---

## DR-0018-01: 8081 management API contract details (pagination, filtering, admin gating, errors)

**Status:** Open

**Context**
- ADR-0018 defines the existence and purpose of 8081 but does not fully specify the *contract*.
- `gsd-browser/docs/api/HTTP_API.md` currently contains example shapes, not a pinned schema.

**Decision needed**
- Pin the stable contract for listing and inspection endpoints so CLI and operators can depend on it.

**Spec items to pin**
- Pagination: cursor format (opaque string), stability guarantees, and max limits.
- Sorting: default order (e.g., `created_at desc`), and whether the API supports alternate sorts.
- Filtering: supported query params (`status`, `since`, `tool_name`, etc.) and validation behavior.
- Admin gating: what flags/env vars/scopes enable `--all` (cross-identity) access.
- Error model: stable JSON error payload format + HTTP status usage with non-enumerability semantics.

**Follow-up tasks**
- Promote example payloads in `gsd-browser/docs/api/HTTP_API.md` to a pinned contract section.
- Add JSON schemas for 8081 responses if we want machine-checkable guarantees (optional).

---

## DR-SEC-01: Identity extraction + admin model (8080 MCP HTTP and 8081 management REST)

**Status:** Open

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

---

## DR-JOBS-01: Standardize compat job timeout/error payloads

**Status:** Open

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

