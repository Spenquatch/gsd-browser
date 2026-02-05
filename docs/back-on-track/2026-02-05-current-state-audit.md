# GSD Browser — Current State Audit & Reconciliation (2026-02-05)

This report treats `docs/back-on-track/current.md` as a hypothesis and validates claims against the repository
and (where possible) the live Azure configuration.

---

## 0) Immediate Red Flags (secrets / credential exposure risk)

### IaC outputs expose live credentials
Multiple Bicep modules **output secrets**, which makes them retrievable from deployment outputs by
anyone with access to those deployments (and increases accidental logging risk):

- Redis primary key + full `rediss://:KEY@host:port/0` URL:
  - `infra/modules/redis.bicep:91` (`output redisPrimaryKey`)
  - `infra/modules/redis.bicep:92` (`output docketUrl`)
- Storage account key: `infra/modules/storage.bicep:104` (`output secretAccessKey`)
- Log Analytics shared key: `infra/modules/log-analytics.bicep:22` (`output sharedKey`)
- ACR admin password: `infra/modules/acr.bicep:27` (`output acrPassword`)

**Impact:** high-severity credential exfiltration path; also contradicts an expected “never
emit secrets” operational posture.

---

## 1) Current Reality (verified)

### 1.1 Jobs queueing/processing (MCP API → Redis/Docket → worker)

**What’s implemented**

- “Compat job” submission is a dedicated MCP tool surface that schedules Docket tasks and persists
  a durable mapping:
  - Tool entrypoints: `gsd-browser/src/gsd_browser/fastmcp_v2_stdio.py:391` (`web_eval_agent_submit`),
    plus `job_get`/`job_wait` wrappers starting at `gsd-browser/src/gsd_browser/fastmcp_v2_stdio.py:481`.
  - Submission logic: `gsd-browser/src/gsd_browser/optionb/compat_jobs.py:96` (`submit_job`)
    pre-allocates `task_id` + `session_id`, builds a Docket task key, and calls `docket.add(...)`.
  - Durable job mapping (job_id ↔ task_key): `gsd-browser/src/gsd_browser/optionb/job_store.py:181`
    (`create_job`) and `gsd-browser/src/gsd_browser/optionb/job_store.py:77` (`JobStore.write`).

- Job status transitions and `started_at` are derived from Docket execution state:
  - `gsd-browser/src/gsd_browser/optionb/compat_jobs.py:215` (`job_get`) maps `ExecutionState`
    → `queued|running|completed|failed|cancelled` and reads `execution.started_at`.
  - Mgmt REST “job snapshot” does the same: `gsd-browser/src/gsd_browser/optionb/ops_jobs.py`
    (notably `_snapshot_for_record`).

- Worker entrypoint is FastMCP v2 (Option B), and applies the Redis 6.0 `XAUTOCLAIM` compat patch:
  - Patch: `gsd-browser/src/gsd_browser/optionb/docket_redis_compat.py:15`
    (`apply_xautoclaim_compat_patch`).
  - Wired into worker: `gsd-browser/src/gsd_browser/cli.py:232` (`worker` command).

**Azure runtime config observed (prod)**

- `gsd-prod-api` is HTTP transport, no execution: `GSD_TRANSPORT=http`,
  `FASTMCP_DOCKET_CONCURRENCY=0` (observed via `az containerapp show`).
- `gsd-prod-worker` runs `gsd-browser worker` (observed via `az containerapp show` command/args).
- Redis version is **6.0** (supports the rationale for the `XAUTOCLAIM` patch): `az redis show`
  reports `redisVersion=6.0`.

**Brittle assumptions / mismatches**

- The Redis 6.0 patch monkey-patches `redis.asyncio` behavior globally
  (`docket_redis_compat.py:15`). That’s pragmatic, but a long-term maintenance risk (library
  upgrades, partial compatibility).

---

### 1.2 Sessions listing (Mgmt API `/api/v1/sessions`) and why it works now

**What’s implemented**

- Session listing is derived from **TaskOwnershipRecord** keys in Redis:
  - Key pattern hardcoded: `gsd-browser/src/gsd_browser/management_api/app.py:396`
    (`pattern = "gsd:v1:tasks:*:owner"`).
  - Listing + aggregation (status `create|active|terminated`):
    `gsd-browser/src/gsd_browser/management_api/app.py:435` (`_sessions_payload`).

- Compat job submission now *best-effort* persists TaskOwnershipRecords so those sessions become
  listable:
  - Persist on submit: `gsd-browser/src/gsd_browser/optionb/compat_jobs.py:96`
    (writes via `task_ownership` store; failure is swallowed with a log).
  - Record/store: `gsd-browser/src/gsd_browser/optionb/task_ownership.py`
    (`TaskOwnershipRecord`, `TaskOwnershipStore.write`).

**Brittle assumptions / mismatches**

- **Scalability:** `_read_task_ownership_records` uses Redis `SCAN` over the *global* keyspace and
  filters client-side (`management_api/app.py`). This will degrade with scale and tenant count.
- “Terminated sessions until TTL” is effectively “until the TaskOwnershipRecord expires”
  (via `pexpireat` in `task_ownership.py`), not a durable session model.

---

### 1.3 Screenshots/artifacts persistence + retrieval (and the Redis fallback)

**What’s implemented**

- Step screenshots are captured during agent execution and persisted as artifacts:
  - Capture + persist call sites:
    - `gsd-browser/src/gsd_browser/mcp_server.py:1038` (nested `record_step_screenshot`)
    - `gsd-browser/src/gsd_browser/mcp_server.py:1170` / `gsd-browser/src/gsd_browser/mcp_server.py:1214`
      (calls to `persist_screenshot`)
  - Persist implementation: `gsd-browser/src/gsd_browser/optionb/screenshot_artifacts.py:66`
    (`persist_screenshot`).

- Artifact index and per-session zset:
  - Index writer + “pending → ready” finalize: `gsd-browser/src/gsd_browser/optionb/artifact_index.py`
    (`ArtifactWriter.write`, `ArtifactIndexStore.finalize_ready`).

- Azure Blob endpoint forces a deliberate fallback to Redis-backed blob storage:
  - Endpoint compatibility check: `gsd-browser/src/gsd_browser/optionb/screenshot_artifacts.py:33`
    (`_endpoint_is_probably_s3_compatible` returns false for `*.blob.core.windows.net`).
  - Redis blob key format is implemented as: `gsd:v1:artifacts:{artifact_id}:blob`
    (`screenshot_artifacts.py`).

- Retrieval:
  - Mgmt API endpoint supports `include_data=true` for Redis-backed screenshots:
    `gsd-browser/src/gsd_browser/management_api/app.py:571` (`_list_session_screenshots`).
  - MCP tool retrieval exists too: `gsd-browser/src/gsd_browser/mcp_server.py:2618`
    (`get_screenshots`), reading Redis when `s3_bucket == "redis"`.

**Brittle assumptions / mismatches**

- **Cleanup is S3-centric:** `CleanupRunner` deletes blobs via a `delete_s3(...)` callback, but
  Redis-backed blobs rely on TTL expiry; the cleanup code path is misleading/fragile if extended.
- **Operational risk:** storing image blobs in Redis + setting Redis `maxmemory-policy` to `noeviction`
  in IaC (`infra/modules/redis.bicep`) creates a failure mode where the platform stops accepting
  writes when memory fills (jobs can fail in surprising ways).

---

### 1.4 Dashboard auth + build-time config (Clerk + Vite)

**What’s implemented**

- Build-time Clerk key gating and “misconfigured build” UI:
  - `gsd-dashboard/src/main.tsx:8` reads `import.meta.env.VITE_CLERK_PUBLISHABLE_KEY` and renders an
    explicit error page if missing.

- Token acquisition:
  - `gsd-dashboard/src/lib/auth.ts:4` reads `VITE_GSD_CLERK_JWT_TEMPLATE` and tries
    `getToken({ template })` with fallback to the default token.

- Management API base URL:
  - `gsd-dashboard/src/lib/api.ts:3` uses `VITE_GSD_API_BASE_URL` to call `/api/v1/sessions` and
    `/api/v1/sessions/:id/screenshots`.

**Brittle assumptions / mismatches**

- Vite env vars are compile-time; Azure Static Web Apps “app settings” won’t fix an already-built
  bundle (matches `docs/back-on-track/current.md`).
- `gsd-dashboard/dist/` is present in-repo and may embed production values (publishable keys are
  meant to be public, but committing build output increases drift and review noise).

---

### 1.5 Streaming (current deployed behavior vs code)

**What’s actually deployed (verified)**

- The **worker ingress on port 5009 serves a plain-text “ok” health server**, not the streaming
  FastAPI/Socket.IO server:
  - This matches the worker CLI health server behavior in `gsd-browser/src/gsd_browser/cli.py:232`.

**What exists in code (but is not “prod ready” as-is)**

- A streaming server with session rooms + join/leave and a SessionRegistry:
  - `gsd-browser/src/gsd_browser/streaming/server.py`
  - `gsd-browser/src/gsd_browser/streaming/session_registry.py`
- “JWT mode” scaffolding:
  - `gsd-browser/src/gsd_browser/streaming/security.py:220` (`authorize_socket_connection`)
  - `_authorize_jwt`: `gsd-browser/src/gsd_browser/streaming/security.py:329`

**Key mismatch vs ADR intentions**

- JWT streaming auth is **not actually wired to verify JWTs in the server connect handler**:
  - `_authorize_jwt` requires a `jwt_verifier`, but `streaming/server.py` calls
    `authorize_socket_connection` without passing `jwt_verifier` / `sid_identity_map`
    (`gsd-browser/src/gsd_browser/streaming/server.py:157` / `gsd-browser/src/gsd_browser/streaming/server.py:158`).
  - Net effect: enabling `GSD_STREAMING_AUTH_MODE=jwt` would fail connections (or never establish
    verified identities), contradicting ADR-0023/0024 expectations.

---

## 2) Deltas vs ADRs/Plans (expected → actual → risk/impact)

| Area | Expected (ADR/Plan) | Actual (code + prod) | Risk / Impact |
|---|---|---|---|
| Azure Blob “S3-compatible” artifacts | ADR-0025 claims Blob S3-compat works for `S3Client` | Code explicitly treats `*.blob.core.windows.net` as incompatible and falls back to Redis blobs (`screenshot_artifacts.py:33`, `screenshot_artifacts.py:66`) | Long-term cost/reliability risk; Redis memory pressure and operational coupling |
| Artifact storage design | ADR-0009 says “keep binaries out of Redis; store in object storage” | Redis is storing screenshot blobs (by design fallback) | Breaks scale economics; increases blast radius (Redis outage = queue + artifacts outage) |
| Streaming auth (JWT mode) | ADR-0023/Plan: JWT verified on Socket.IO connect, sid→Identity map | JWT mode not fully implemented/wired (`security.py:220`, `server.py:157`) and not deployed | “View Live” cannot be hardened for SaaS; risk of insecure/incorrect auth if rushed |
| Remote streaming architecture | ADR-0024: workers expose Socket.IO; session affinity routing; session-aware health endpoints | Prod worker exposes health server only; no session-aware health endpoint; mgmt `stream_url` usually null unless configured | Missing key SaaS feature; architecture decision not realized operationally |
| Multi-session model | ADR-0026: per-session control + per-session streamer + lifecycle cleanup | SessionRegistry exists (`session_registry.py`), but streaming server is not deployed and control/streamer remain largely singleton-based | Concurrency + isolation gaps; inconsistent behavior vs docs/plan |
| Sessions listing scalability | ADR-0018 suggests secondary index for identity-scoped listing | Mgmt scans Redis keys (`management_api/app.py:396`, `management_api/app.py:435`) | Latency/Redis load grows with tenants/tasks; operability issues |
| Env var naming consistency | ADR-0022/0025 use `GSD_JWT_JWKS_URI` | Implementation uses `GSD_JWT_JWKS_URL` | Operator confusion + misconfig risk; docs drift |
| Release process | Plan implies reproducible infra + CI/CD | Prod uses manual image tags and manual SWA build-time env process | Release safety risk; hard to audit provenance and roll back safely |
| Secrets hygiene | ADRs imply safe secret handling | IaC outputs multiple secrets (`infra/modules/*`) | High-severity security issue; increases likelihood of credential compromise |

---

## 3) Risk Register (severity + evidence)

### Security
- **HIGH — Secret exfil via IaC outputs**:
  `infra/modules/redis.bicep:91`, `infra/modules/redis.bicep:92`,
  `infra/modules/storage.bicep:104`, `infra/modules/log-analytics.bicep:22`,
  `infra/modules/acr.bicep:27`.
- **HIGH — Long-lived bearer tokens are effectively non-revocable** (documented in dashboard UI and
  `docs/TOKEN_GENERATION_PLAN.md`); increases blast radius of token theft.
- **MED — Mgmt API origin/host hardening can block non-browser ops tooling**:
  `gsd-browser/src/gsd_browser/optionb/http_hardening.py:142` (and prod mgmt lacks
  `GSD_HTTP_ALLOW_NULL_ORIGIN`).

### Reliability
- **HIGH — Redis is a single point of failure for both queue and (fallback) artifact blobs**
  (Option B architecture + Redis blob fallback in `screenshot_artifacts.py:66`).
- **MED — Redis 6.0 compatibility relies on monkey-patching `redis-py`**:
  `docket_redis_compat.py:15` (fragile across dependency updates).
- **MED — Sessions listing relies on SCAN** which can degrade under load:
  `management_api/app.py:396`, `management_api/app.py:435`.

### Scalability
- **HIGH — Session enumeration is O(N keys)** due to global scan + JSON parse; will degrade with
  tenant/task volume: `management_api/app.py:396`, `management_api/app.py:435`.
- **MED — Artifact delivery uses base64 in REST responses** when Redis-backed
  (`include_data=true` in `management_api/app.py:571`), creating large payload and UI/perf risk.

### Cost
- **HIGH — Redis memory cost pressure from storing images** (blob fallback). Combined with
  `noeviction` intent in IaC (`infra/modules/redis.bicep`) risks “writes start failing” instead of
  graceful eviction.
- **MED — Manual deploy + drift** increases human time cost and error rate.

### Operability
- **HIGH — Manual dashboard deploy requires build-time env correctness**; SWA config cannot patch
  Vite build-time env post-build (`gsd-dashboard/src/main.tsx:8` guard helps but doesn’t prevent drift).
- **MED — Streaming architecture is “in repo but not productized”**; risk of partial enablement
  without correct JWT wiring.

---

## 4) Hardening Roadmap Proposal (next 5–10 steps)

1) **Stop emitting secrets in infra outputs** (dependency: none; research: low) — remove/avoid
   outputs for Redis keys, storage keys, Log Analytics shared key, ACR password; pass secrets
   directly into `containerApps.secrets` without surfacing them as outputs.
2) **Rotate compromised/at-risk credentials** (dependency: #1 plan + confirmation; research:
   medium) — Redis keys, storage keys, ACR admin password, Log Analytics shared key; verify no
   downstream dependencies break.
3) **Implement native Azure Blob artifact store adapter** (dependency: decision; research: medium/high)
   — replace Redis blob fallback with real object storage (managed identity or SAS), and switch
   dashboard to thumbnails via signed URLs rather than base64 by default.
4) **Add identity-scoped secondary index for sessions** (dependency: none; research: low) — avoid
   Redis SCAN by writing `ZSET tenants:{t}:subjects:{s}:sessions` at job submit time; update mgmt
   listing to use it.
5) **Decide streaming production shape** (dependency: product decision; research: high) — dedicated
   stream app vs worker-embedded; define session affinity mechanism and health endpoints; match
   ADR-0024 or update ADR to match new plan.
6) **Fix JWT streaming auth wiring before enabling it** (dependency: #5 if streaming is pursued;
   research: low/medium) — connect handler must verify JWT and populate `sid→Identity` map; add
   tests and a “fail closed” mode.
7) **Unify release process (CI/CD + pinned image tags)** (dependency: #1 if secrets handling changes;
   research: medium) — pipeline builds backend image tags immutably and deploys via IaC; dashboard
   build injects Vite env values via CI secrets.
8) **Reconcile doc drift** (dependency: none; research: low) — correct `GSD_JWT_JWKS_URI` →
   `GSD_JWT_JWKS_URL` in ADRs, remove `GSD_REDIS_URL` references per ADR-0016, update ADR-0025’s
   Blob “S3-compat” claim.
9) **Add observability for queue health + artifact pressure** (dependency: #3/#4 helpful; research:
   medium) — metrics for queued age, running count, failure rate, and artifact bytes written; alerts
   + runbooks.

---

## 5) Questions / Unknowns (not provable from repo alone)

- **Was the Redis password actually logged in prod, and when?** Needs Container App log retention
  queries or Log Analytics search scoped to specific revisions.
- **Actual Redis memory usage + eviction/write-failure behavior in prod** (given blob fallback +
  `noeviction` intent). Needs Azure Redis metrics + maxmemory configuration confirmation.
- **Clerk JWT templates and role→scope configuration**: dashboard assumes templates like `gsd-24h`,
  `gsd-7d`, etc (`gsd-dashboard/src/pages/TokensPage.tsx`), but correctness depends on Clerk
  dashboard configuration.
- **Whether any consumers depend on IaC secret outputs today** (e.g., scripts reading deployment
  outputs). Needs operator confirmation.

---

## Appendix: Key code pointers (by subsystem)

**Jobs / Queue**
- Submit + durable mapping: `gsd-browser/src/gsd_browser/optionb/compat_jobs.py:96`,
  `gsd-browser/src/gsd_browser/optionb/job_store.py:181`
- Job state polling: `gsd-browser/src/gsd_browser/optionb/compat_jobs.py:215`,
  `gsd-browser/src/gsd_browser/optionb/compat_jobs.py:392`
- Worker entrypoint + Redis compat patch: `gsd-browser/src/gsd_browser/cli.py:232`,
  `gsd-browser/src/gsd_browser/optionb/docket_redis_compat.py:15`

**Sessions (Mgmt API)**
- SCAN-based listing + aggregation: `gsd-browser/src/gsd_browser/management_api/app.py:396`,
  `gsd-browser/src/gsd_browser/management_api/app.py:435`
- Task ownership model: `gsd-browser/src/gsd_browser/optionb/task_ownership.py`

**Artifacts (Screenshots)**
- Persist + Azure Blob incompat detection: `gsd-browser/src/gsd_browser/optionb/screenshot_artifacts.py:33`,
  `gsd-browser/src/gsd_browser/optionb/screenshot_artifacts.py:66`
- Step screenshot capture callsites: `gsd-browser/src/gsd_browser/mcp_server.py:1038`,
  `gsd-browser/src/gsd_browser/mcp_server.py:1170`
- Screenshot retrieval (Mgmt): `gsd-browser/src/gsd_browser/management_api/app.py:571`
- Artifact index + cleanup: `gsd-browser/src/gsd_browser/optionb/artifact_index.py`

**HTTP hardening / auth**
- Origin/Host middleware: `gsd-browser/src/gsd_browser/optionb/http_hardening.py:142`
- MCP HTTP auth middleware: `gsd-browser/src/gsd_browser/optionb/http_auth.py`
- HTTP ASGI entrypoint: `gsd-browser/src/gsd_browser/fastmcp_v2_http.py:33`

**Dashboard**
- Clerk build-time guard: `gsd-dashboard/src/main.tsx:8`
- JWT template selection: `gsd-dashboard/src/lib/auth.ts:4`
- Mgmt API base URL wiring: `gsd-dashboard/src/lib/api.ts:3`

**Infra (credential exposure)**
- Redis key + docket URL outputs: `infra/modules/redis.bicep:91`, `infra/modules/redis.bicep:92`
- Storage key output: `infra/modules/storage.bicep:104`
- Log Analytics shared key output: `infra/modules/log-analytics.bicep:22`
- ACR password output: `infra/modules/acr.bicep:27`
