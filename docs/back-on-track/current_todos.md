# Back-on-Track TODOs (Airtight Completion) — 2026-02-06

This is the **single, detailed checklist** to fully complete `docs/recent_plan.md` and close the
remaining correctness/security gaps identified by comparing that plan to the current codebase.

Scope:
- Includes remaining work across **Phases 1–4** (not just Phase 4).
- Favors “make it hard to regress” (tests, docs, and verification steps), not just “make it work”.

If you’re a fresh agent/operator:
- Start by reading:
  - `docs/recent_plan.md` (source-of-truth plan)
  - `docs/back-on-track/2026-02-05-current-state-audit.md` (what triggered the plan)
  - `docs/back-on-track/current.md` (prod snapshot; may need updates as part of this TODO list)
- Then use this file as the “do the work” checklist.

---

## Current status snapshot (as of 2026-02-06)

Implemented (high confidence):
- IaC refactor to eliminate secret outputs from nested module outputs.
- Secret redaction utility + removal of raw URL leaks in error paths.
- Mgmt/API null-Origin allowance via env var (server-to-server tooling support).
- Redis memory monitoring alert + runbooks.
- Azure Blob artifact persistence + signed URL retrieval paths.
- Identity-scoped session/task indexes (with SCAN fallback).
- `/metrics` endpoint (JWT-admin gated) and alert stubs.
- CI/CD workflows for backend + deploy + dashboard.

Known gaps / not “airtight” yet:
- Artifact cleanup is **S3-only** and does not delete Azure blobs or Redis blobs.
- `/api/v1/sessions` has **no pagination** but indexed path effectively caps results to 50 sessions.
- Mgmt screenshot presign TTL is hard-coded (ignores `GSD_PRESIGNED_URL_TTL_S`).
- Azure SAS generation depends on **user delegation keys**; role/permission assumptions are not validated.
- Plan-requested docs and tests are missing (e.g. `DATA_MODEL.md`, `test_azure_blob_client.py`).
- Some “current state” docs are now stale and can mislead operators.

---

## Prerequisites (so you can actually execute this)

### Local dev toolchain

- Python 3.11+ and `uv` installed (recommended). Repo root Make targets assume this.
- Optional (for integration tests): Docker + Docker Compose.

Commands you will run frequently:
- `make py-dev`
- `make py-lint`
- `make py-test`
- `make py-smoke`

Integration harnesses (optional but recommended before prod changes):
- Redis/Valkey: `cd gsd-browser && make redistest-up` (or `docker compose -f docker/compose.redistest.yml up -d`)
- S3 compat harness: see skip messages from pytest; start the referenced compose stack when needed.

### Azure access (for deploy/rotation validation)

- Azure CLI authenticated (`az login`) and correct subscription selected.
- Permission to:
  - Read and update Container Apps (secrets/env vars/revisions)
  - Rotate Redis/Storage/ACR credentials
  - Read Log Analytics (and possibly regenerate keys via REST)
  - Assign RBAC roles (if adjusting managed identity permissions)

Concrete environment defaults in this repo (confirm before executing):
- Prod resource group/prefix/location are defined in `infra/parameters/prod.bicepparam`.
- Container App names are derived from `prefix`:
  - `${prefix}-api`, `${prefix}-worker`, `${prefix}-mgmt` (default prefix is `gsd-prod`)

### GitHub (for CI/CD execution)

- Ability to configure secrets/environments described in `docs/ops/CI-CD.md`.

---

## Key file map (where changes will likely land)

### IaC / deployment
- `infra/main.bicep`
- `infra/modules/aca-app-*.bicep`
- `infra/modules/monitoring.bicep`
- `infra/modules/storage-rbac.bicep`
- `infra/scripts/deploy.sh`
- `.github/workflows/*.yml`

### Python backend (Option B)
- Artifacts:
  - `gsd-browser/src/gsd_browser/optionb/screenshot_artifacts.py`
  - `gsd-browser/src/gsd_browser/optionb/artifact_index.py`
  - `gsd-browser/src/gsd_browser/optionb/azure_blob_client.py`
  - `gsd-browser/src/gsd_browser/management_api/app.py` (REST screenshots + metrics + sessions list)
  - `gsd-browser/src/gsd_browser/mcp_server.py` (MCP get_screenshots)
- Session indexing:
  - `gsd-browser/src/gsd_browser/optionb/task_ownership.py`
  - `gsd-browser/src/gsd_browser/management_api/app.py` (sessions payload)
- Streaming:
  - `gsd-browser/src/gsd_browser/streaming/server.py`

### Dashboard
- Screenshots rendering: `gsd-dashboard/src/pages/LiveSessionPage.tsx`
- API client: `gsd-dashboard/src/lib/api.ts`

---

## Tenant-specific values (where to look, don’t guess)

When a step needs “the real prod value”, use these sources in priority order:
1. `docs/back-on-track/current.md` (intended to be an operator snapshot)
2. `infra/parameters/prod.bicepparam` (IaC desired state)
3. Azure CLI (source of truth for deployed state)

Useful Azure CLI discovery commands (examples):
- List container apps:
  - `az containerapp list -g gsd-prod-rg -o table`
- Get principal IDs (managed identities):
  - `az containerapp show -g gsd-prod-rg -n gsd-prod-api --query identity.principalId -o tsv`
- Check RBAC assignments on storage:
  - `az role assignment list --assignee <principalId> --scope <storageAccountResourceId> -o table`

---

## Phase 1 — Security (Critical)

### 1.2 Credential rotation (execute + verify)

- [x] Perform rotation for Redis, Storage keys, ACR password, Log Analytics shared key using:
  - `docs/ops/RUNBOOK-credential-rotation.md`
  - Executed 2026-02-07: Redis (secondary regen → update apps → primary regen), Storage (key2 regen → update api+worker → key1 regen), ACR (password2 regen → update all 3 → password regen), Log Analytics (secondary shared key via REST API query param workaround).
- [x] Post-rotation: verify **all three** apps consume the updated secrets:
  - `docket-url`: api, worker, mgmt — all healthy, Running status confirmed
  - `acr-password`: api, worker, mgmt — all healthy, Running status confirmed
  - `s3-secret-access-key`: **api and worker** — both healthy
- [x] Post-rotation: query Log Analytics for historical secret leakage patterns and confirm "no new hits"
  since rotation time (document the exact query used).
  - KQL: `ContainerAppConsoleLogs_CL | where TimeGenerated > datetime(2026-02-07T16:03:00Z) | where Log_s has "password" or Log_s has "secret" or Log_s has "rediss" | where not(Log_s has "healthz") | project TimeGenerated, ContainerAppName_s, Log_s | top 20 by TimeGenerated`
  - Result: 0 rows (no new leaks post-rotation). Historical leaks all reference now-invalidated keys.

### 1.3 Secret-handling docs wiring

- [x] Ensure `docs/SECURITY.md` is referenced from `CLAUDE.md` (and/or other contributor docs) so the
  guidance is discoverable during development.

### 1.1 IaC “no secret outputs” regression guard

- [x] Add a deterministic guard that fails CI if any `infra/modules/*.bicep` declares secret-ish outputs:
  - Pattern examples: `output .*key`, `output .*secret`, `output .*password`, `output .*token`
  - Ensure the guard does **not** flag benign outputs like `accessKeyId` when it is not a secret.
- [x] Add “how to run locally” instructions in `infra/README.md` (or `docs/ops/CI-CD.md`) for the guard.
  - Suggested implementation: a small shell script under `infra/scripts/` and a CI step in
    `.github/workflows/deploy-prod.yml` (or a lint workflow).

### 1.4 Origin hardening defense-in-depth (tooling/scripts)

- [x] Update `gsd-browser/scripts/prod_*.sh` scripts to always send an `Origin:` header
  (even though mgmt now allows null origin) to reduce policy surprises.
- [x] Add a short note in `docs/SECURITY.md` explaining why scripts include `Origin`.

### 1.5 Artifact retention guardrails (while Redis fallback exists)

- [x] Re-evaluate `GSD_RETENTION_SECONDS_PROD` default and document the chosen value/rationale.
- [x] Add an explicit operator note in `docs/ops/RUNBOOK-redis-memory.md` about retention tuning as the
  first lever before manual cleanup/scaling.

---

## Phase 2 — Reliability & Cost

### 2.1 Azure Blob artifact store (finish + harden)

#### Decision required (blocker): What is the "airtight" deletion/retention strategy?

Decision made 2026-02-07: **Option A (app-driven) + storage lifecycle safety net.**
- [x] Source of truth retention policy:
  - **Option A chosen**: Application-driven deletion (cleanup runner deletes blobs by backend type)
  - Storage lifecycle policy added as belt-and-suspenders (14 days, 2x app-side 7-day retention)
- [x] Storage lifecycle rule documented in `docs/back-on-track/current.md`:
  - Policy: `delete-old-artifacts` on `gsdprodstore`, all `blockBlob`, 14 days after modification.

#### 2.1.A Fix multi-backend cleanup (must-delete)

Artifact cleanup currently routes all deletions through “S3 delete” only and will leak Azure blobs.

- [x] Update cleanup to delete by backend type:
  - `artifact_backend == "azure"`: delete blob via `AzureBlobClient.delete(blob_name=...)`
  - `artifact_backend == "s3"`: delete via S3 client (current behavior)
  - `artifact_backend == "redis"`: delete Redis blob key (best-effort), or document TTL-only strategy
- [x] Make cleanup tolerant:
  - “Not found” should not fail the whole cleanup loop.
  - Backend misconfig should surface via structured logs and metrics (if possible).
- [x] Add tests for cleanup deletion routing:
  - Ensure a record with `artifact_backend="azure"` triggers Azure delete.
  - Ensure legacy records (no `artifact_backend`) still infer correctly.
  - Ensure “not found” deletes do not fail cleanup.

#### 2.1.B Presign TTL configuration parity

- [x] Mgmt endpoint `/api/v1/sessions/{id}/screenshots` should respect `GSD_PRESIGNED_URL_TTL_S`
  (and/or a query param) instead of hard-coding 900 seconds.
- [x] Add tests for TTL parsing and bounds (mirror MCP tool behavior).

#### 2.1.C Azure SAS “user delegation” feasibility + fallback

Azure presigning via Managed Identity often requires user delegation key permissions.

- [x] Validate in prod (or staging) whether the assigned managed identities can call
  `get_user_delegation_key` successfully.
- [x] If not viable, pick and implement one fallback (document decision):
  - Option 1: Assign additional role (likely “Storage Blob Data Delegator”) to API identity.
  - Option 2: Use connection-string signing for presign only (`GSD_AZURE_STORAGE_CONNECTION_STRING`).
  - Option 3: Add an authenticated “artifact proxy” endpoint on mgmt/api to stream bytes to the dashboard.
- [x] Update `docs/adr/ADR-0025-azure-reference-deployment.md` “Implementation Notes” to reflect the chosen
  SAS signing approach and operational implications (rotation vs RBAC).
  - Also update `docs/back-on-track/current.md` with the *actual* chosen approach and how to verify it.

#### 2.1.D Tests requested by plan

- [x] Add `gsd-browser/tests/test_azure_blob_client.py` with mocks for:
  - upload (`put_bytes`)
  - download (`get_bytes`)
  - SAS generation (`generate_sas_url`) success + failure modes

### 2.2 Identity-scoped session/task indexes (finish + correctness)

#### 2.2.A Fix `/api/v1/sessions` pagination + truncation

Right now, indexed lookup defaults to `limit=50` but the endpoint offers no way to request more,
which can silently hide sessions once indexes exist.

- [x] Implement `limit` and `offset` query params on `/api/v1/sessions`
  - Default `limit=50`, max `200`
- [x] Maintain backward compatibility:
  - Keep response as an array
  - Add `X-Total-Count` response header (recommended by the plan)
  - Do not change response shape without coordinating dashboard/client updates.
- [x] Add tests covering:
  - default limit behavior
  - `limit/offset` correctness
  - header presence/values when index exists
  - SCAN fallback remains functional

#### 2.2.B Document the data model

- [x] Create `gsd-browser/docs/DATA_MODEL.md` containing:
  - Key formats for ownership records and indexes:
    - `gsd:v1:tasks:{task_id}:owner`
    - `gsd:v1:tenants:{t}:subjects:{s}:sessions:z`
    - `gsd:v1:tenants:{t}:subjects:{s}:sessions:{sid}:tasks:z`
    - Artifact index keys and zsets
  - Retention/TTL rules and “max expiry” behavior for indexes
  - Back-compat rules (legacy inference)

#### 2.2.C Make session status aggregation explicit

- [x] Document how session `status` is derived from task states (queued/running/completed/failed/cancelled)
  in `gsd-browser/docs/DATA_MODEL.md` (or a small comment block in the code near `_sessions_payload_*`).

#### 2.2.D (Optional) Performance/load validation

- [ ] Add a small, repeatable load check (not necessarily a full benchmark suite) that demonstrates
  indexed lookup avoids global SCAN at scale (10k+ tasks across tenants).

---

## Phase 3 — Streaming & Features (Prod readiness)

### 3.3 Control-plane JWT + authorization (verify prod parity)

- [x] Ensure docs reflect that the worker runs **combined streaming + health** on port 5009 when enabled:
  - Update `docs/back-on-track/current.md` (it is currently stale on this point).
- [x] Add/confirm acceptance criteria (documented + repeatable):
  - valid JWT connects to `/stream` and `/ctrl`: **Verified 2026-02-07.** Both namespaces enforce JWT via `authorize_socket_connection` → `_verify_socket_jwt_identity` (`streaming/server.py:207-279`). Missing/invalid token → `ConnectionRefusedError("unauthorized")`. Legacy dashboard `/dashboard` returns HTTP 401 without JWT.
  - tenant mismatch cannot take control / send input: **Verified 2026-02-07.** `_ctrl_session_authorized` (`server.py:400-452`) compares `identity.tenant_id` against `session.owner_tenant_id`; mismatch → `"forbidden"`. Same check in `join_session` for `/stream` (`server.py:811-827`).
  - control semantics preserved ("pause on take control"): **Verified 2026-02-07.** `ControlState(auto_pause_on_take_control=True)` is the default (`control_state.py:26-39`). `take_control()` auto-pauses (`control_state.py:167-173`); `release_control()` unpauses (`control_state.py:175-180`).

---

## Phase 4 — Release process & Observability

### 4.1 CI/CD tightening

- [x] Decide fate of legacy `.github/workflows/azure-deploy.yml`:
  - Keep (and document why), or
  - Remove/rename to reduce confusion
- [x] Add a minimal "required checks" list in `docs/ops/CI-CD.md`:
  - `make py-lint`, `make py-test`, `make fe-lint` (if feasible in CI), etc.

### 4.2 Documentation drift final sweep (keep plan promises)

- [x] Confirm ADR/doc references are correct and consistent:
  - `rg -n "GSD_JWT_JWKS_URI" docs gsd-browser/docs` should be empty
  - `rg -n "GSD_REDIS_URL" docs gsd-browser/docs` should be empty or explicitly marked "deprecated"
- [x] Ensure `docs/recent_plan.md` stays in-repo and is the referenced plan for future agents.

### 4.3 Alerts “real receivers” + runbook linkage

- [x] Configure alert action group receivers (email/webhook) and document who is paged vs notified.
  - Added `ops-primary` email receiver (`spmcconnell.totaltele@gmail.com`) to `gsd-prod-alerts-ag` (live + IaC in `monitoring.bicep`).
- [x] Validate scheduledQueryRules queries against actual Log Analytics table schemas in your workspace:
  - Confirmed `ContainerAppConsoleLogs_CL` and `ContainerAppSystemLogs_CL` both exist and return data.
  - **BUG FOUND/FIXED**: `worker-failures` and `queue-backlog` queries had literal `${prefix}-worker` instead of `gsd-prod-worker` (Bicep triple-quoted strings don't interpolate). Fixed in `infra/modules/monitoring.bicep` (switched to single-line interpolated strings). Live fix via REST API was rate-limited; will take effect on next IaC deploy.
- [x] Add a small "alert drill" checklist in each runbook (how to acknowledge, what graphs to check first).
  - Added to: `RUNBOOK-worker-failures.md`, `RUNBOOK-queue-backlog.md`, `RUNBOOK-redis-memory.md`.

### 4.3.5 Redis XAUTOCLAIM compat visibility (informational)

- [x] Add a non-paging informational alert/query for the `redis.xautoclaim_unsupported` signal so it's
  easy to confirm the compat path is (or is not) in use.
  - Document the exact Log Analytics query in `docs/ops/RUNBOOK-worker-failures.md` or a dedicated note.

---

## “Airtight” verification checklist (run before calling it done)

### Local (repo)
- [x] `make py-lint`
- [x] `make py-test`
- [x] `make py-smoke`
- [x] `make fe-lint` — N/A (no dashboard code changes in this pass)

### IaC (no-secret outputs)
- [x] `./infra/scripts/deploy.sh --what-if` succeeds
- [x] Root deployment outputs contain **no secrets**:
  - Validate by searching outputs for `key|secret|password|token` and by manual review
- [x] Confirm nested module outputs contain **no secrets** (enforced by CI guard)

### Prod/staging runtime
- [x] Dashboard:
  - Sessions list: Mgmt API `/api/v1/sessions` supports `limit`/`offset` with `X-Total-Count` header (verified in code, 2.2.A completed earlier). Dashboard at `https://browse.buildconnectors.com` returns HTTP 200.
  - Screenshots: Azure Blob-backed artifacts use User Delegation SAS via Managed Identity (RBAC verified 2026-02-06). Code path in `azure_blob_client.py`.
- [x] Streaming:
  - `/stream` and `/ctrl` require JWT in prod (`GSD_STREAMING_AUTH_MODE=jwt`). Tenant isolation enforced via `_ctrl_session_authorized` and `join_session` tenant checks. Legacy dashboard returns HTTP 401 without JWT.
- [x] Observability:
  - `/metrics` returns HTTP 401 without JWT (confirmed 2026-02-07). Requires `gsd:admin` scope.
  - Alert queries validated against actual Log Analytics schemas: all 3 queries (`container-restart-loop`, `worker-failures`, `queue-backlog`) execute successfully and return expected result shapes. Alert drill checklists added to all runbooks.

---

## Documentation updates (to keep operators from getting misled)

- [x] Update `docs/back-on-track/current.md` to reflect current reality (streaming/worker behavior, artifact
  backend behavior, cleanup strategy, and any operational decisions made above).
- [x] When this TODO list reaches "done", add a short "Plan completed" note at the top of
  `docs/recent_plan.md` (or create a `docs/back-on-track/COMPLETED.md`) with:
  - Date completed
  - Commands run locally (`make py-*`, etc.)
  - Deploy workflow(s) used
  - Any remaining known risks explicitly accepted
  - **Done**: See `docs/back-on-track/COMPLETED.md`.
