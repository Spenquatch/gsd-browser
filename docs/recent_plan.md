# GSD Browser - Back on Track Plan

Based on audit: `docs/back-on-track/2026-02-05-current-state-audit.md`

## Overview

This plan addresses 9 hardening steps identified in the audit, organized into 4 phases by priority.
We will execute phase-by-phase, with detailed subtasks for each.

---

## Phase 1: Security (Critical - Do First)

### 1.1 Remove Secret Outputs from IaC (Not Just @secure)

**Problem**: Bicep modules output secrets, making them retrievable from `az deployment show` outputs.
**Note**: `@secure()` on outputs only masks display; it doesn't prevent retrieval. We must eliminate secret outputs entirely.

**Current State** (verified):
```
infra/modules/redis.bicep:91-92
  output redisPrimaryKey string = redis.listKeys().primaryKey
  output docketUrl string = 'rediss://:${redis.listKeys().primaryKey}@...'

infra/modules/storage.bicep:104
  output secretAccessKey string = storage.listKeys().keys[0].value

infra/modules/log-analytics.bicep:22
  output sharedKey string = workspace.listKeys().primarySharedKey

infra/modules/acr.bicep:27
  output acrPassword string = acr.listCredentials().passwords[0].value
```

**How Secrets Flow** (main.bicep):
```
redis.outputs.docketUrl  apiApp, mgmtApp, workerApp params
storage.outputs.secretAccessKey  apiApp, workerApp params (both!)
logAnalytics.outputs.sharedKey  acaEnv params
acr.outputs.acrPassword  all app params
```

**Better Design**: Consuming modules reference resources as `existing` and call `listKeys()` directly, writing secrets straight to `containerApps.secrets` without passing through module outputs.

**Subtasks**:

#### 1.1.1 Refactor redis.bicep - remove secret outputs entirely
- [ ] Remove `redisPrimaryKey` and `docketUrl` outputs
- [ ] Keep only non-secret outputs: `redisHost`, `redisPort`, `redisId` (resource ID)
- File: `infra/modules/redis.bicep`

#### 1.1.2 Refactor storage.bicep - remove secret outputs entirely
- [ ] Remove `secretAccessKey` output
- [ ] Keep only non-secret outputs: `storageAccountName`, `blobEndpoint`, `accessKeyId`, `storageId`
- File: `infra/modules/storage.bicep`

#### 1.1.3 Refactor log-analytics.bicep - remove secret outputs entirely
- [ ] Remove `sharedKey` output
- [ ] Keep only: `workspaceId`, `customerId`
- File: `infra/modules/log-analytics.bicep`

#### 1.1.4 Refactor acr.bicep - remove secret outputs entirely
- [ ] Remove `acrPassword` output
- [ ] Keep only: `acrId`, `acrName`, `acrLoginServer`, `acrUsername`
- File: `infra/modules/acr.bicep`

#### 1.1.5 Update ACA app modules to reference resources as `existing`
- [ ] In `aca-app-worker.bicep`: reference Redis + Storage + ACR as `existing` resources
- [ ] Call `listKeys()` / `listCredentials()` directly inside the module
- [ ] Write secrets directly to `configuration.secrets[]`
- [ ] Files: `infra/modules/aca-app-worker.bicep`, `aca-app-api.bicep`, `aca-app-mgmt.bicep`

#### 1.1.6 Update aca-environment.bicep for Log Analytics
- [ ] Reference Log Analytics workspace as `existing`
- [ ] Call `listKeys()` directly for shared key
- File: `infra/modules/aca-environment.bicep`

#### 1.1.7 Update main.bicep - stop passing secrets as parameters
- [ ] Remove secret parameters from module invocations
- [ ] Pass only resource IDs/names for `existing` references
- File: `infra/main.bicep`

#### 1.1.8 Verify deploy.sh only prints non-secret outputs
- [ ] Root outputs in main.bicep should be non-secret (FQDNs, names, etc.)
- [ ] Verify `az deployment sub show --query properties.outputs` shows no secrets
- File: `infra/scripts/deploy.sh`

#### 1.1.9 Verify NO module deployments output secrets (CRITICAL)
- [ ] After refactor, verify ALL modules in `infra/modules/*.bicep` have no secret outputs
- [ ] `listKeys()`/`listCredentials()` calls will still exist in deployment graph (that's fine)
- [ ] But they must NEVER appear in any module's `output` declarations
- [ ] Verify `deploy.sh` does NOT query module deployments' outputs (only root)
- [ ] Test: `az deployment group list -g gsd-prod-rg --query "[].{name:name}" -o table`  don't query outputs of nested deployments

---

### 1.2 Rotate Compromised Credentials

**Problem**: Credentials may have been exposed in deployment outputs and logs.

**Subtasks**:

#### 1.2.1 Document current credential consumers (CORRECTED)
- [ ] Verify all Container Apps using each secret via `az containerapp show`:
  - `docket-url`: gsd-prod-api, gsd-prod-worker, gsd-prod-mgmt (all three)
  - `acr-password`: all three apps
  - `s3-secret-access-key`: gsd-prod-api AND gsd-prod-worker (BOTH, not just worker!)
  - `log-analytics-shared-key`: ACA environment only

#### 1.2.2 Create rotation runbook (with validated commands)
- [ ] Write step-by-step runbook for rotating each credential type
- [ ] **Validate exact Azure CLI commands before documenting**:
  - Redis: `az redis regenerate-key --key-type Primary|Secondary`
  - Storage: `az storage account keys renew --key primary|secondary`
  - ACR: `az acr credential renew --name <acr> --password-name password|password2`
  - Log Analytics: `az monitor log-analytics workspace get-shared-keys` (then regenerate via portal or API)
- [ ] Include verification steps for each rotation
- [ ] Include rollback procedure
- [ ] File: create `docs/ops/RUNBOOK-credential-rotation.md`

#### 1.2.3 Rotate Redis keys (EXAMPLE - confirm exact syntax before execution)
- [ ] Example: `az redis regenerate-key -n gsd-prod-redis -g gsd-prod-rg --key-type Secondary`
- [ ] **Validate exact command syntax before running**
- [ ] Update `docket-url` secret in all 3 Container Apps to use secondary key
- [ ] Verify all apps healthy
- [ ] Then regenerate Primary key (as backup)
- [ ] Verify workers reconnect successfully

#### 1.2.4 Rotate Storage keys (EXAMPLE - confirm exact syntax before execution)
- [ ] Example: `az storage account keys renew -n gsdprodstore -g gsd-prod-rg --key secondary`
- [ ] **Validate exact command syntax before running**
- [ ] Update `s3-secret-access-key` in BOTH api AND worker Container Apps
- [ ] Verify artifact uploads continue (worker) and artifact retrieval (API)
- [ ] Then regenerate primary key

#### 1.2.5 Rotate ACR password (EXAMPLE - confirm exact syntax before execution)
- [ ] Example: `az acr credential renew -n gsdprodacr --password-name password2`
- [ ] **Validate exact command syntax before running**
- [ ] Update `acr-password` in all Container Apps
- [ ] Verify next deployment can pull images

#### 1.2.6 Rotate Log Analytics key
- [ ] Get current keys: `az monitor log-analytics workspace get-shared-keys -n gsd-prod-logs -g gsd-prod-rg`
- [ ] **Validate regeneration method before execution**:
  - CLI: Check if `az monitor log-analytics workspace regenerate-shared-key` exists (may not be available)
  - If no CLI: Use REST API: `POST /subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.OperationalInsights/workspaces/{ws}/regenerateSharedKey?api-version=2020-08-01`
  - If REST fails: Document as "portal only" and include portal path
- [ ] Document exact method in runbook before treating as executable step
- [ ] Update ACA environment configuration with new key
- [ ] Verify logs continue flowing to Log Analytics
- [ ] File: `docs/ops/RUNBOOK-credential-rotation.md` (document exact method)

---

### 1.3 Review Secret Handling in Logs

**Problem**: Code may print sensitive URLs/credentials to logs.

**Known Issues Found**:
```
gsd-browser/src/gsd_browser/optionb/task_backend.py:25
  raise RuntimeError(f"...url={raw!r}")  # Prints full URL with password on misconfig
```
**Note**: This is startup-time misconfig error, not runtime logging. Lower risk than accidental runtime logging of `FASTMCP_DOCKET_URL` elsewhere.

**Existing Redaction Utility** (DO NOT import from cli.py - it's CLI-private):
```
gsd-browser/src/gsd_browser/cli.py:44
  def _redact_url_password(url: str) -> str:
```

**Subtasks**:

#### 1.3.1 Create shared redaction utility module
- [ ] Create `gsd-browser/src/gsd_browser/utils/secrets.py`
- [ ] Move/copy `_redact_url_password()` to `redact_url_password()` (public)
- [ ] Add `redact_sensitive_value()` for generic redaction
- [ ] DO NOT import from cli.py; create independent implementation

#### 1.3.2 Update cli.py to use shared utility
- [ ] Import from `utils.secrets` instead of local function
- [ ] Keep backward compat with private `_redact_url_password` alias
- File: `gsd-browser/src/gsd_browser/cli.py`

#### 1.3.3 Fix task_backend.py to redact URL in error
- [ ] Import `redact_url_password` from `utils.secrets`
- [ ] Use in error message at line 25
- File: `gsd-browser/src/gsd_browser/optionb/task_backend.py`

#### 1.3.4 Comprehensive audit for secret logging
- [ ] Search patterns: `log.*docket`, `log.*url`, `print.*key`, `raise.*url`, `FASTMCP_DOCKET_URL`
- [ ] Priority files to audit:
  - `config.py` -  looks clean
  - `docket_redis_compat.py` -  only logs error messages, not URLs
  - `management_api/app.py:263` -  sets `Docket(url=...)` but does NOT log it (not a leak)
  - `cli.py:299` - prints URL suggestion in error - ok (no password)
  - `cli.py:452` -  already uses `_redact_url_password()` when printing
  - Any error message that includes raw URLs (like task_backend.py:25)
- [ ] Real leak surfaces are: error messages with raw URLs, explicit logging of `fastmcp.settings.docket.url`
- [ ] Verify: no code path logs docket.url without redaction

#### 1.3.5 Create safe logging checklist
- [ ] Document patterns to avoid (raw URLs, API keys, credentials in logs/errors)
- [ ] Create `docs/SECURITY.md` with guidelines
- [ ] Reference in CLAUDE.md

---

### 1.4 Fix Management API Origin Hardening (Missing Item)

**Problem**: Mgmt API returns `{"error":"origin_not_allowed"}` for requests without `Origin` header, breaking server-to-server tooling and CLI scripts.

**Current Behavior**:
- `gsd-browser/src/gsd_browser/optionb/http_hardening.py:142` enforces origin checks
- Curl without `Origin` header fails

**Options**:
1. Set `GSD_HTTP_ALLOW_NULL_ORIGIN=true` for mgmt Container App
2. Update CLI scripts to always send `Origin` header
3. Adjust hardening middleware to allow server-to-server (no Origin = internal)

**Subtasks**:

#### 1.4.1 Decide origin policy for mgmt API
- [ ] Document decision: which option above?
- [ ] Recommended: Option 1 (allow null origin for mgmt only) - simplest for prod scripts

#### 1.4.2 Implement chosen solution
- [ ] If Option 1: add `GSD_HTTP_ALLOW_NULL_ORIGIN=true` to mgmt Container App env
- [ ] File: `infra/modules/aca-app-mgmt.bicep`

#### 1.4.3 Update CLI scripts to send Origin (defense in depth)
- [ ] Update `gsd-browser/scripts/prod_*.sh` scripts to include `-H "Origin: https://gsd-prod-mgmt..."`
- [ ] Doesn't hurt even if we allow null origin

---

### 1.5 Redis Memory Monitoring (Missing Item - Interim Safeguard)

**Problem**: While artifacts use Redis fallback (before Phase 2 Blob migration), Redis `noeviction` policy risks write failures when memory fills.

**Subtasks**:

#### 1.5.1 Add Redis memory monitoring
- [ ] Create alert for Redis used memory > 80% of max
- [ ] Add to `infra/modules/monitoring.bicep`
- [ ] Link to runbook for manual artifact cleanup

#### 1.5.2 Add artifact retention guardrails
- [ ] Review `GSD_RETENTION_SECONDS_*` defaults (currently 86400 dev, 604800 prod)
- [ ] Consider shorter prod retention while on Redis fallback
- [ ] Document in ops runbook

#### 1.5.3 Create Redis memory pressure runbook
- [ ] `docs/ops/RUNBOOK-redis-memory.md`
- [ ] Document how to identify blob keys (use SCAN, NOT KEYS - KEYS blocks Redis):
  ```bash
  redis-cli --scan --pattern "gsd:v1:artifacts:*:blob" | head -100
  ```
- [ ] Document manual cleanup procedure if needed
- [ ] Include warning: never use `KEYS` in production

---

## Phase 2: Reliability & Cost

### 2.1 Implement Native Azure Blob Artifact Store

**Problem**: Screenshots fall back to Redis (memory pressure, cost, single point of failure).

**Current Flow** (verified):
```
screenshot_artifacts.py:33-38
  _endpoint_is_probably_s3_compatible() returns False for *.blob.core.windows.net

screenshot_artifacts.py:100-112
  If S3 config exists but endpoint not S3-compat  log warning, use Redis

screenshot_artifacts.py:146-172
  Redis blob: SET gsd:v1:artifacts:{id}:blob + PEXPIREAT
```

**Subtasks**:

#### 2.1.1 Create Azure Blob client adapter
- [ ] Add `azure-storage-blob` to pyproject.toml dependencies
- [ ] Create `gsd-browser/src/gsd_browser/optionb/azure_blob_client.py`
- [ ] Implement: `AzureBlobClient` class with `put_bytes()`, `get_bytes()`, `generate_sas_url()`
- [ ] Support auth via: env var connection string, managed identity, or SAS token

#### 2.1.2 Add Azure Blob detection to screenshot_artifacts.py
- [ ] Update `_endpoint_is_probably_s3_compatible()` to detect Azure Blob
- [ ] Add new path for Azure Blob when `*.blob.core.windows.net` detected
- [ ] File: `gsd-browser/src/gsd_browser/optionb/screenshot_artifacts.py`

#### 2.1.3 Implement Azure Blob persist path
- [ ] Add Azure Blob upload in `persist_screenshot()` (line ~100)
- [ ] Keep S3 and Redis paths as fallbacks
- [ ] Priority: Azure Blob  S3  Redis

#### 2.1.4 Update artifact retrieval to use signed URLs
- [ ] Update `management_api/app.py:571` (`_list_session_screenshots`)
- [ ] For Azure Blob artifacts: return `presigned_url` (or `url`) instead of `data_base64`
- [ ] Keep `data_base64` for Redis-backed artifacts (no presigned URL possible)

#### 2.1.4a Update gsd-dashboard to prefer presigned_url (REQUIRED)
- [ ] Update dashboard screenshot rendering to prefer `presigned_url`/`url` over `data_base64`
- [ ] Handle mixed backends gracefully: some artifacts may have URL, others base64
- [ ] Fallback logic: if `presigned_url` exists use it, else use `data_base64`
- [ ] File: `gsd-dashboard/src/...` (screenshot rendering component)

#### 2.1.5 Define artifact backend contract (NEW)
**Decision needed**: How to store backend type in ArtifactIndexRecord?

Current fields: `s3_bucket`, `s3_key` (S3-centric)

**Options**:
- A: Overload existing fields: `s3_bucket="azure"`, `s3_key` = blob name
- B: Add `artifact_backend` enum field: `"s3" | "azure" | "redis"`
- C: Add explicit `azure_container`, `azure_blob` fields

**Recommendation**: Option B - cleanest, extensible

- [ ] Decide on approach (document in ADR or code comment)
- [ ] Update `ArtifactIndexRecord` model in `artifact_index.py`
- [ ] **Back-compat rule**: if `artifact_backend` field is missing, treat as legacy:
  - If `s3_bucket == "redis"`  Redis backend
  - Else  S3 backend (inferred from existing `s3_bucket`/`s3_key` fields)
  - This ensures old records don't break retrieval
- [ ] Update persist logic in `screenshot_artifacts.py`
- [ ] Update retrieval in `management_api/app.py` and `mcp_server.py`

#### 2.1.6 Update IaC env vars for Azure Blob
- [ ] Add env vars to worker Container App:
  - `GSD_ARTIFACT_BACKEND=azure` (new)
  - Auth config (see 2.1.6a below)
- [ ] Also add to API Container App (for retrieval)
- [ ] Keep S3 env vars as fallback option
- [ ] File: `infra/modules/aca-app-worker.bicep`, `aca-app-api.bicep`

#### 2.1.6a Define Azure Blob auth mode (REQUIRED DECISION)
**Choose one auth approach**:

| Option | Pros | Cons |
|--------|------|------|
| A: Managed Identity + RBAC | No secrets to rotate, Azure-native | Requires identity setup + role assignment |
| B: Connection string | Simple, works today | Another secret to manage/rotate |
| C: SAS token | Fine-grained, expiring | Token rotation complexity |

**Recommended**: Option A (Managed Identity)

**Subtasks for Option A**:
- [ ] Enable system-assigned managed identity on API + worker Container Apps
- [ ] Assign `Storage Blob Data Contributor` role to identity on storage account
- [ ] **RESEARCH REQUIRED**: Confirm MI can generate user delegation SAS in this subscription:
  - `generate_sas_url()` (plan 2.1.1) typically uses user delegation keys with MI
  - May require additional role: `Storage Blob Data Delegator` (beyond Contributor)
  - If MI SAS not viable: fallback to (B) connection string for signing, or serve bytes through API
- [ ] Configure Azure Blob client to use `DefaultAzureCredential`
- [ ] No connection string env var needed (identity handles auth)
- [ ] Update IaC: `infra/modules/aca-app-worker.bicep`, `aca-app-api.bicep`
- [ ] Update IaC: `infra/modules/storage.bicep` to grant RBAC (and potentially Delegator role)

**If Option B (connection string)**:
- [ ] Add `GSD_AZURE_STORAGE_CONNECTION_STRING` env var as secret
- [ ] Include in credential rotation runbook

#### 2.1.7 Add Azure Blob client tests
- [ ] Create test file `gsd-browser/tests/test_azure_blob_client.py`
- [ ] Mock Azure Blob SDK calls
- [ ] Test upload, download, SAS URL generation

#### 2.1.8 Update Mgmt and MCP retrieval for multi-backend
- [ ] `management_api/app.py:571` - handle `artifact_backend` field
- [ ] `mcp_server.py` get_screenshots - handle `artifact_backend` field
- [ ] Return appropriate URL format based on backend

#### 2.1.9 Update cleanup semantics for new backend (IMPORTANT)
**Current State**: `CleanupRunner` assumes S3 deletion callbacks via `delete_s3()`.
- [ ] Review cleanup code in `artifact_index.py` for S3 assumptions
- [ ] Add Azure Blob deletion callback
- [ ] Add Redis blob deletion callback (if not relying solely on TTL)
- [ ] Ensure orphan handling doesn't regress with new backends
- [ ] File: `gsd-browser/src/gsd_browser/optionb/artifact_index.py`

---

### 2.2 Add Identity-Scoped Secondary Indexes for Sessions AND Tasks

**Problem**: Mgmt API uses Redis SCAN over global keyspace - O(N) and degrades with scale.

**Current Flow** (verified):
```
management_api/app.py:396-432 (_read_task_ownership_records)
  SCAN cursor pattern "gsd:v1:tasks:*:owner"
  Filter by tenant_id/subject_id CLIENT-SIDE
   Scans ALL tasks, then filters

management_api/app.py:449-498 (_sessions_payload)
  For each session, iterates task ownership records to get task_ids/tool_names
  Then queries Docket runs hash per task to compute session status
   Needs tasks per session, not just sessions per identity
```

**Solution**: TWO indexes needed to fully eliminate SCAN:
1. `gsd:v1:tenants:{t}:subjects:{s}:sessions:z` - sessions by identity
2. `gsd:v1:tenants:{t}:subjects:{s}:sessions:{sid}:tasks:z` - tasks by session

**Subtasks**:

#### 2.2.1 Define complete index key structure
- [ ] Session index: `gsd:v1:tenants:{tenant_id}:subjects:{subject_id}:sessions:z`
  - ZSET with: member=session_id, score=created_at_ms
- [ ] Task index per session: `gsd:v1:tenants:{tenant_id}:subjects:{subject_id}:sessions:{session_id}:tasks:z`
  - ZSET with: member=task_id, score=created_at_ms
- [ ] Document in `gsd-browser/docs/DATA_MODEL.md`

#### 2.2.2 Update TaskOwnershipStore.write() to maintain BOTH indexes
- [ ] Add ZADD to session index (member=session_id, score=created_at_ms)
- [ ] Add ZADD to task index (member=task_id, score=created_at_ms)
- [ ] **Index expiry strategy** (choose one):

  **Option A: Key-level expiry with max rule** (recommended if retention is variable):
  - Get current key expiry: `PTTL <index_key>`
  - Set new expiry = `max(current_expiry, new_member_expiry_ms)`
  - Use `PEXPIREAT <index_key> <new_expiry>`
  - This prevents accidentally expiring an index that still has newer members

  **Option B: Fixed retention window with score pruning** (simpler if retention is fixed):
  - No key-level expiry
  - Prune by score cutoff: `ZREMRANGEBYSCORE <index_key> -inf <(now_ms - retention_window_ms)>`
  - Works cleanly because score = created_at_ms and retention is fixed

  - [ ] Decide which option; document in code
- [ ] All in same pipeline transaction
- [ ] File: `gsd-browser/src/gsd_browser/optionb/task_ownership.py:42-63`

#### 2.2.3 Create indexed lookup methods
- [ ] `list_sessions_by_identity(identity, limit, offset)`  list[session_id]
  - Use ZREVRANGE on session index
- [ ] `list_tasks_by_session(identity, session_id)`  list[task_id]
  - Use ZRANGE on task index
- [ ] Add to TaskOwnershipStore class

#### 2.2.4 Update _sessions_payload to use indexed lookups
- [ ] Get session_ids from session index (not SCAN)
- [ ] For each session, get task_ids from task index
- [ ] Then batch-fetch TaskOwnershipRecords with MGET
- [ ] File: `gsd-browser/src/gsd_browser/management_api/app.py:435-498`

#### 2.2.5 Maintain backward compatibility
- [ ] If index is empty (pre-migration data), fall back to SCAN
- [ ] Log deprecation warning when falling back
- [ ] Add migration script to backfill indexes for existing records (optional)

#### 2.2.6 Add pagination support (backward-compatible)
- [ ] Add `limit` and `offset` query params to `/api/v1/sessions`
- [ ] Default limit: 50, max: 200
- [ ] Return `total_count` using ZCARD on session index
- [ ] **Backward compatibility decision** (avoid breaking existing dashboard/clients):
  - Option A: Keep response as array, add `X-Total-Count` header (recommended - minimal change)
  - Option B: Gate new response shape behind `?include_meta=1` query param
  - Option C: New endpoint `/api/v2/sessions` with different shape
- [ ] Decide and document approach before implementation

#### 2.2.7 Define session status aggregation rules (make implicit explicit)
**Current implicit rules** in `_sessions_payload`:
- Session status derived from task states: `queued`, `running`, `completed`, `failed`
- "active" = any task running; "terminated" = all tasks done; "create" = initial state

- [ ] Document explicit aggregation rules in code comments or `DATA_MODEL.md`
- [ ] Define how multiple tasks per session  single session status
- [ ] Ensure indexed lookup produces same aggregation results as SCAN-based

#### 2.2.8 Consider identity  tasks index (optional, for ops)
**Optional but useful** for future `/api/v1/tasks` listing:
- Key: `gsd:v1:tenants:{tenant_id}:subjects:{subject_id}:tasks:z`
- ZSET with: member=task_id, score=created_at_ms
- [ ] Decide: add now or defer to future ops work
- [ ] If adding: update TaskOwnershipStore.write() to maintain this index too

#### 2.2.9 Test indexed lookup performance
- [ ] Create load test with 10K+ tasks across multiple tenants
- [ ] Verify indexed lookup is O(1) per tenant vs O(N) total
- [ ] Verify session status aggregation produces identical results

---

## Phase 3: Streaming & Features

### 3.1 Decide Streaming Production Architecture

**Problem**: Streaming code exists but isn't deployed/productized.

**Current Deployed State**:
- Worker port 5009: serves health endpoint only (not streaming server)
- `stream_url` in session response: usually `null` unless `GSD_STREAMING_PUBLIC_HOST` set
- Dashboard "View Live" button: non-functional in prod

**Options Analysis**:

| Option | Pros | Cons |
|--------|------|------|
| A: Dedicated `gsd-prod-stream` app | Clean separation, independent scaling | Extra infra, routing complexity |
| B: Embed in worker | Simpler infra, session affinity natural | Mixed concerns, resource contention |

**Subtasks**:

#### 3.1.1 Write ADR for streaming architecture decision
- [ ] Create `docs/adr/ADR-00XX-streaming-production-architecture.md`
- [ ] Document chosen approach (recommend Option B for simplicity)
- [ ] Define session affinity requirements
- [ ] Define `stream_url` format and computation

#### 3.1.2 Design combined health + streaming server (COMPLEX)

**Current State**:
- Worker CLI (`cli.py:232`) runs minimal health server on port 5009
- ACA ingress routes to port 5009
- Streaming server is a separate FastAPI+Socket.IO app (`streaming/server.py`)

**Challenge**: Need single process that serves:
- `/healthz` - for ACA liveness probes
- `/` - Socket.IO streaming
- Any other REST endpoints

**Subtasks**:
- [ ] Design unified ASGI app that combines health + streaming
- [ ] Options:
  - A: Mount health routes on streaming FastAPI app
  - B: Use ASGI middleware to multiplex
  - C: Keep separate but run both in same process on different ports (complex)
- [ ] Recommended: Option A - add `/healthz` route to streaming server.py
- [ ] Ensure Docket worker loop runs in background, not blocking ASGI
- [ ] File: `gsd-browser/src/gsd_browser/streaming/server.py`

#### 3.1.3 Update worker CLI to use streaming server
- [ ] Modify `gsd-browser worker` command to start streaming server instead of minimal health server
- [ ] Start Docket task loop as background task
- [ ] Configure `GSD_STREAMING_BIND_HOST=0.0.0.0` for external access
- [ ] File: `gsd-browser/src/gsd_browser/cli.py` (worker command)

#### 3.1.4 Configure Container App for streaming
- [ ] Update `aca-app-worker.bicep` to expose port 5009 for Socket.IO
- [ ] Sticky sessions already configured: `stickySessions.affinity: 'sticky'` 
- [ ] Add `GSD_STREAMING_PUBLIC_HOST` env var
- [ ] Verify transport is `auto` to support WebSocket upgrade
- [ ] **Add streaming security env vars**:
  - `GSD_STREAMING_AUTH_MODE=jwt` (enable JWT auth for production)
  - `STREAMING_ALLOWED_ORIGINS=https://browse.buildconnectors.com,https://zealous-wave-0ed3a980f.1.azurestaticapps.net`
    (see `streaming/security.py:73` - defaults to "allow all" when unset)
- [ ] File: `infra/modules/aca-app-worker.bicep`

#### 3.1.4a Acceptance Criteria: Don't Break Worker Health (CRITICAL)
**Non-negotiable requirements**:
- [ ] `/healthz` remains 200 OK on port 5009 (ACA liveness probe)
- [ ] Socket.IO connect/emit works without blocking Docket worker loop
- [ ] Docket task processing continues while streaming connections are active
- [ ] ACA ingress + sticky sessions continue to work
- [ ] Test: submit job while streaming connected, job completes successfully

#### 3.1.5 Standardize stream_url format (API consistency)

**Current Inconsistency**:
- `management_api/app.py` returns base URL (no `/stream`)
- `mcp_server.py:_build_stream_url` returns URL with `/stream`
- Dashboard normalizes, but API should be consistent

**Subtasks**:
- [ ] Decide canonical format: base URL or full namespace URL?
- [ ] Recommended: return base URL, client appends namespace as needed
- [ ] Update both mgmt API and MCP server to use same format
- [ ] Document in ADR

---

### 3.2 Fix JWT Streaming Auth Wiring

**Problem**: `authorize_socket_connection` called without `jwt_verifier` / `sid_identity_map`.

**Current Flow** (verified):
```
streaming/server.py:157-167 (connect handler)
  authorize_socket_connection(
    ...
    jwt_verifier=None,        #  NOT PASSED
    sid_identity_map=None,    #  NOT PASSED
  )

streaming/security.py:272-281
  if config.auth_mode == "jwt":
    return _authorize_jwt(..., jwt_verifier, sid_identity_map)

streaming/security.py:340-344
  if jwt_verifier is None:
    logger.error("JWT auth mode enabled but no jwt_verifier configured")
    return False  #  ALWAYS REJECTS
```

**Subtasks**:

#### 3.2.1 Create JWT verifier factory for streaming
**Reusable pieces** (correct references):
- `GsdJwtVerifier` class: `gsd-browser/src/gsd_browser/optionb/identity.py:98`
- Env-var wiring examples:
  - `gsd-browser/src/gsd_browser/fastmcp_v2_http.py:49`
  - `gsd-browser/src/gsd_browser/management_api/app.py:133`

- [ ] Create `get_jwt_verifier()` function that uses `GsdJwtVerifier` with same JWKS/issuer/audience config
- [ ] **Prerequisite**: Ensure worker Container App has same JWT env vars as mgmt/API:
  - `GSD_JWT_JWKS_URL`
  - `GSD_JWT_ISSUER`
  - `GSD_JWT_AUDIENCE`
- [ ] Update `infra/modules/aca-app-worker.bicep` to include these env vars
- [ ] File: create `gsd-browser/src/gsd_browser/streaming/jwt_auth.py`

#### 3.2.1a Fix broken import in streaming server (SEPARATE ISSUE)
**Problem**: `streaming/server.py:567` imports `get_jwt_verifier` from `optionb/identity.py`, but that function does NOT exist.
- [ ] Either: create `get_jwt_verifier()` in `identity.py` (preferred, centralizes verifier creation)
- [ ] Or: fix the import to use the correct path
- [ ] This is separate from the Socket.IO connect wiring problem
- [ ] File: `gsd-browser/src/gsd_browser/streaming/server.py:567`

#### 3.2.2 Add sid_identity_map to streaming server
- [ ] Create `sid_identity_map: dict[str, Identity]` at server init
- [ ] Populate in connect handler AFTER verification succeeds (not in `_authorize_jwt()` - see 3.2.3)
- [ ] Clean up on disconnect

#### 3.2.3 Implement JWT verification in connect handler (OPTION B - NOW)

**Current broken state**:
- `_authorize_jwt()` in `security.py:329-395` does NOT verify JWT
- Just stashes `{"_pending_token": token}` and returns True
- Identity is NOT populated

**Implementation (Option B - async verification in connect handler)**:

```python
# In streaming/server.py:156 (async connect handler)
@sio.event(namespace=DEFAULT_STREAM_NAMESPACE)
async def connect(sid: str, environ: dict[str, Any], auth: dict[str, Any] | None) -> None:
    # 1. Preflight (sync): rate-limit + origin check + ensure auth["token"] present
    if not authorize_socket_connection(...):  # security.py:220
        raise ConnectionRefusedError("unauthorized")

    # 2. Verify (async): JWT verification
    token = auth.get("token") if auth else None
    if config.auth_mode == "jwt" and token:
        try:
            identity = await verifier.verify(token)  # GsdJwtVerifier from identity.py:98
        except Exception:
            raise ConnectionRefusedError("unauthorized")
        # 3. On success: store resolved identity (no _pending_token staging)
        sid_identity_map[sid] = identity

    # ... rest of handler
```

**Subtasks**:
- [ ] Create `get_jwt_verifier()` in `optionb/identity.py` (or adjust import in `streaming/server.py:567`)
- [ ] Use `GsdJwtVerifier` with env vars: `GSD_JWT_JWKS_URL`, `GSD_JWT_ISSUER`, `GSD_JWT_AUDIENCE`
- [ ] Env wiring examples: `fastmcp_v2_http.py:49`, `management_api/app.py:133`
- [ ] Populate `sid_identity_map[sid]` with resolved Identity on success
- [ ] Clean up `sid_identity_map` on disconnect
- [ ] On failure: `raise ConnectionRefusedError("unauthorized")`
- [ ] Files: `streaming/server.py:156-167`, `security.py`, `optionb/identity.py`

#### 3.2.4 Add streaming auth integration tests
- [ ] Test: JWT mode with valid token  accepted, identity populated in sid_identity_map
- [ ] Test: JWT mode with invalid token  ConnectionRefusedError("unauthorized")
- [ ] Test: JWT mode with missing token  rejected
- [ ] Test: Origin rejected when `STREAMING_ALLOWED_ORIGINS` set and origin not in list
- [ ] Test: Rate limiting works (connect spam rejected)
- [ ] File: `gsd-browser/tests/test_streaming_auth.py`

#### 3.2.5 Add tenant isolation for streaming
- [ ] Verify connected client can only receive events for their session
- [ ] Use `sid_identity_map` to check tenant ownership before emitting
- [ ] File: `gsd-browser/src/gsd_browser/streaming/server.py`

---

### 3.3 Ensure "Take Control" Stays Working (CRITICAL)

**Why this matters**: /ctrl namespace is separate from /stream and also needs JWT auth + authorization.

#### 3.3.1 Apply same JWT auth to /ctrl connect handler
**Current state**: `/ctrl` connect (`server.py:370-380`) calls `authorize_socket_connection()` without JWT verifier.
In JWT mode this will fail closed.

- [ ] Implement JWT verification in `/ctrl` connect handler (same as /stream)
- [ ] Use same `GsdJwtVerifier` and `sid_identity_map`
- [ ] File: `gsd-browser/src/gsd_browser/streaming/server.py:370`

#### 3.3.2 Enforce tenant/session authorization for control actions
**Problem**: Even with JWT auth, need to verify caller owns the session.

**Authorization rule**: Only session owner's tenant (and optionally subject) can:
- `take_control`, `pause_agent`, `resume_agent`
- Send `input_*` events

**Where to enforce** (in /ctrl event handlers):
- `take_control`: `server.py:392`
- `pause_agent`/`resume_agent`: `server.py:430` / `server.py:447`
- `_handle_ctrl_input_event`: `server.py:318`

**How to check ownership**:
- [ ] Get active session ID from `ControlState` (`control_state.py:39`)
- [ ] Cross-check ownership via `SessionRegistry` (`session_registry.py:132`)
  - Tracks `owner_tenant_id` / `owner_subject_id` (`session_registry.py:57-58`)
- [ ] If no active session, reject control requests with structured error

**Optional hardening (multi-session safety)**:
- [ ] /ctrl event handlers currently ignore payload `session_id` (e.g. `take_control(sid, _: Any)` at `server.py:393`)
- [ ] Dashboard sends `session_id` in payload (`useControlSocket.ts:66`)
- [ ] Consider: require payload `session_id` and ensure it matches `ControlState.active_session_id`
- [ ] This makes multi-session behavior less ambiguous and reduces footguns

#### 3.3.3 Preserve "pause on take control" semantics (don't regress)
**Core UX**: User clicks "Take Control"  agent pauses at next step  queued inputs applied.

**Existing pieces** (verify they remain wired):
- `GSD_AUTO_PAUSE_ON_TAKE_CONTROL` setting: `config.py:84`
- `ControlState.take_control()` sets paused: `control_state.py:167-173`
- `pause_gate` drains/enforces pause: `mcp_server.py:1478-1545`
- `ControlState.wait_until_unpaused()`: `control_state.py:243`

**Evidence that FastMCP v2 tools use pause_gate**:
- `fastmcp_v2_stdio.py:249`  calls `mcp_server.py:750` (web_eval_agent)
- Same path, same `pause_gate` wiring

- [ ] Verify `pause_gate` remains wired in v2/worker execution path
- [ ] Test: take_control flips `control_state.holder_sid` and pauses when configured

#### 3.3.4 Ensure input dispatcher remains cross-thread safe
**Design**: ctrl handlers run on streaming server loop; agent runs on tool execution loop.
`ControlState.dispatch_input_directly()` uses `asyncio.run_coroutine_threadsafe()` (`control_state.py:226`).

**Invariants to maintain**:
- [ ] `ControlState.set_input_dispatcher(dispatch_fn, loop)` called when agent has CDP target (`mcp_server.py:1356-1358`)
- [ ] Dispatcher cleared when run ends (`mcp_server.py:1745-1751`)

#### 3.3.5 Add /ctrl tests and acceptance criteria
- [ ] JWT auth tests:
  - Valid token connects and receives `control_state`
  - Invalid token refused
  - Disallowed Origin refused when `STREAMING_ALLOWED_ORIGINS` set
- [ ] Control semantics tests:
  - `take_control` flips `holder_sid` and pauses when configured
  - Input events rejected if: not holder / not paused / no active session
  - Input events dispatch (directly or queued) when paused
- [ ] File: `gsd-browser/tests/test_streaming_control.py`

---

## Phase 4: Release Process & Observability

### 4.1 Unify Release Process (CI/CD)

**Problem**: Manual image tags, manual SWA build with env vars at build time.

**Current Manual Process**:
```bash
# Backend (from docs/back-on-track/current.md)
TAG="fix-$(date +%s)"
docker build -t gsdprodacr.azurecr.io/gsd-browser:$TAG ...
docker push ...
az containerapp update -n gsd-prod-api ... --image ...:$TAG
az containerapp update -n gsd-prod-worker ... --image ...:$TAG
az containerapp update -n gsd-prod-mgmt ... --image ...:$TAG

# Dashboard
export VITE_CLERK_PUBLISHABLE_KEY="pk_live_..."
npm run build
npx swa deploy ./dist
```

**Subtasks**:

#### 4.1.1 Create GitHub Actions workflow for backend
- [ ] Create `.github/workflows/backend-build.yml`
- [ ] Trigger on push to main, manual dispatch, and tags
- [ ] Build Docker image with immutable tag (git SHA or semver)
- [ ] Push to ACR
- [ ] Store image tag as artifact for deploy workflow

#### 4.1.2 Create GitHub Actions workflow for dashboard
- [ ] Create `.github/workflows/dashboard-build.yml`
- [ ] Inject Vite env vars from GitHub secrets
- [ ] Build and deploy to Azure Static Web App
- [ ] Use Azure/static-web-apps-deploy action

#### 4.1.3 Create deployment workflow
- [ ] Create `.github/workflows/deploy-prod.yml`
- [ ] Require approval for production deploys
- [ ] Update all Container Apps with new image tag
- [ ] Verify health endpoints after deploy

#### 4.1.4 Document rollback procedure
- [ ] Add `docs/ops/ROLLBACK.md`
- [ ] Document how to identify previous image tag
- [ ] Document `az containerapp revision activate` for instant rollback
- [ ] Include verification steps

---

### 4.2 Reconcile Documentation Drift

**Problem**: ADRs reference incorrect env var names, outdated claims.

**Subtasks**:

#### 4.2.1 Fix env var naming in ADRs
- [ ] Search ADRs for `GSD_JWT_JWKS_URI`  replace with `GSD_JWT_JWKS_URL`
- [ ] Search for `GSD_REDIS_URL`  remove/update per ADR-0016
- [ ] Files: `docs/adr/ADR-00*.md`

#### 4.2.2 Fix ADR-0025 Azure Blob claims
- [ ] Update ADR-0025 to clarify Azure Blob is NOT S3-compatible
- [ ] Document the Redis fallback behavior
- [ ] Reference new Azure Blob adapter (from Phase 2)
- [ ] File: `docs/adr/ADR-0025-*.md`

#### 4.2.3 Update CLAUDE.md with current env vars
- [ ] Review `CLAUDE.md` env var documentation
- [ ] Add any missing env vars from config.py
- [ ] Remove deprecated env vars
- [ ] File: `/CLAUDE.md`

#### 4.2.4 Consolidate env var documentation
- [ ] Create single source of truth: `gsd-browser/docs/ENV_VARS.md`
- [ ] Include all env vars with descriptions, defaults, and examples
- [ ] Reference from CLAUDE.md and .env.example

#### 4.2.5 Fix dashboard build artifact policy (Missing Item)
**Problem**: `gsd-dashboard/dist/` is committed to repo, may embed prod values and increases review noise.

**Options**:
- A: Keep committing dist/ (document why)
- B: Add `gsd-dashboard/dist/` to `.gitignore`, build in CI only

**Subtasks**:
- [ ] Decide policy (recommend Option B)
- [ ] If B: Add to `.gitignore`
- [ ] If B: Remove existing `dist/` from git history (optional, can just delete files)
- [ ] Update CI workflow to build and deploy dashboard

---

### 4.3 Add Observability for Queue Health + Artifacts

**Problem**: No visibility into queue depth, worker liveness, artifact pressure.

**Subtasks**:

#### 4.3.1 Define key metrics
- [ ] Queue depth: count of tasks in `queued` state
- [ ] Queue age: time since oldest `queued` task was created
- [ ] Processing latency: time from `queued` to `completed`
- [ ] Failure rate: completed tasks with errors / total completed
- [ ] Artifact storage: Redis memory used by blob keys
- [ ] Active workers: count of workers processing tasks

#### 4.3.2 Expose metrics endpoint
- [ ] Add `/metrics` endpoint to management API (Prometheus format)
- [ ] Query Docket/Redis for queue stats
- [ ] Include artifact storage stats
- [ ] File: `gsd-browser/src/gsd_browser/management_api/app.py`
- [ ] **Operability decisions**:
  - Who scrapes it in ACA? Options: Azure Monitor Container Insights, external Prometheus, self-hosted
  - Require auth / IP allowlist? Options:
    - A: Bearer token auth (reuse JWT)
    - B: IP allowlist via ACA network rules
    - C: Public but rate-limited (risk: data leak)
  - Recommended: Option A (JWT) or B (IP allowlist) - don't expose unauthenticated

#### 4.3.3 Set up Azure Monitor alerts
- [ ] Configure Log Analytics query alerts for:
  - Queue age > 5 minutes
  - Failure rate > 10%
  - Worker health failures
- [ ] Update `infra/modules/monitoring.bicep`

#### 4.3.4 Create operational runbooks
- [ ] `docs/ops/RUNBOOK-queue-backlog.md` - What to do when queue backs up
- [ ] `docs/ops/RUNBOOK-worker-failures.md` - Troubleshooting worker issues
- [ ] `docs/ops/RUNBOOK-redis-memory.md` - Handling Redis memory pressure
- [ ] Link runbooks to alert action groups

#### 4.3.5 Add Redis 6.0 XAUTOCLAIM compat monitoring (IMPORTANT)

**Background**: Worker applies monkeypatch for Redis 6.0 XAUTOCLAIM compat (`docket_redis_compat.py:15`).
We need to monitor for: (a) compat path in use, (b) worker failures, (c) redelivery not happening.

**Log alerts to add**:
- [ ] `redis.xautoclaim_unsupported` (compat in use) - Source: `docket_redis_compat.py:57-59`
  - **Note**: This is logged ONCE per worker process (not per task)
  - Alert type: "seen in last 24h" (informational, not paging)
  - Actual paging should rely on backlog/canary signals (below)
- [ ] `Docket worker stopped unexpectedly` (worker died) - Source: `cli.py:390`
- [ ] `did not enter polling loop` (startup crash) - Source: `cli.py:378`

**Backlog monitoring** (symptom-based, catches any redelivery regression):
- [ ] Enable `GSD_WORKER_DIAGNOSTICS_INTERVAL_S=60` in worker env
- [ ] **Alert threshold options** (avoid noisy "queue_len > 0" alerts):
  - Option A: Alert on `docket_queue_len` increasing for N consecutive intervals (jobs stuck)
  - Option B: Add "oldest queued age" diagnostic to `worker.docket.depth` log path (`cli.py:395`)
    and alert on "oldest > 5m" (more precise)
  - Recommended: Option B if feasible, else Option A
- [ ] Source: `cli.py:403` emits `worker.docket.depth`

**Canary job** (optional, high-signal):
- [ ] Scheduled "submit tiny job  expect completion < X minutes" health check
- [ ] If fails, page - this reliably detects redelivery regressions the XPENDING/XCLAIM fallback might miss

---

## Verification Checklist

### Phase 1 Verification (Security)
```bash
# 1.1 Verify IaC no longer outputs secrets
az deployment sub show --name <deployment> \
  --query "properties.outputs" -o json | grep -i "key\|secret\|password"
# Should return empty or only non-sensitive values

# 1.2 Verify credential rotation
az containerapp show -n gsd-prod-worker -g gsd-prod-rg \
  --query "properties.template.containers[0].env" -o table
# Verify apps are healthy after rotation

# 1.3 Verify no secrets in logs
az monitor log-analytics query -w <workspace-id> \
  --analytics-query "ContainerAppConsoleLogs | where Log contains 'rediss://' | take 10"
# Should return empty
```

### Phase 2 Verification (Reliability & Cost)
```bash
# 2.1 Verify screenshots stored in Azure Blob
# Submit a job, then list blobs with prefix matching build_screenshot_s3_key() semantics:
az storage blob list --account-name gsdprodstore \
  --container-name gsd-artifacts --prefix "tenants/{tenant_id}/subjects/{subject_id}/sessions/"
# Should see screenshot blobs (PNG files)

# 2.2 Verify session listing performance
time curl -H "Authorization: Bearer $TOKEN" \
  "https://gsd-prod-mgmt.../api/v1/sessions"
# Should respond in <100ms

# 2.3 Verify Redis memory stable (use Azure Monitor metrics, not az redis show)
az monitor metrics list \
  --resource "/subscriptions/{sub}/resourceGroups/gsd-prod-rg/providers/Microsoft.Cache/Redis/gsd-prod-redis" \
  --metric "usedmemory" \
  --interval PT1H
# Should not grow with screenshot count after Blob migration
```

### Phase 3 Verification (Streaming)
```bash
# 3.1 Verify stream_url in session response
curl -H "Authorization: Bearer $TOKEN" \
  "https://gsd-prod-mgmt.../api/v1/sessions" | jq '.[0].stream_url'
# Should return a valid wss:// URL

# 3.2 Test streaming auth (use browser devtools or wscat)
# Connect to stream_url with valid JWT  should succeed
# Connect without JWT or with invalid JWT  should fail

# 3.3 Dashboard "View Live" test
# Open dashboard, start a job, click "View Live"  should show stream
```

### Phase 4 Verification (CI/CD & Observability)
```bash
# 4.1 Verify CI/CD
# Push to main  verify GitHub Actions run
# Check ACR for new image tag
# Check Container Apps for updated image

# 4.2 Verify documentation
grep -r "GSD_JWT_JWKS_URI" docs/  # Should return empty
grep -r "GSD_REDIS_URL" docs/      # Should return empty or "deprecated"

# 4.3 Verify alerts
# Simulate high queue depth, verify alert fires
```

---

## Execution Guidance

### Recommended Execution Order

**Start with Phase 1** - Security issues are highest priority:
1. 1.1 (IaC secrets) - Low risk, can deploy immediately
2. 1.2 (Credential rotation) - Do IMMEDIATELY after 1.1 (invalidates exposed outputs)
3. 1.3 (Log secret audit) - Code changes, requires PR review
4. 1.4, 1.5 (Origin, Redis monitoring) - Lower priority within Phase 1

**Then Phase 2** - Reliability improvements:
1. 2.2 (Session index) - Improves existing flow
2. 2.1 (Azure Blob) - New feature, more complex

**Then Phase 3** - Feature enablement:
1. 3.2 (JWT auth fix) - Enables production streaming
2. 3.1 (Architecture) - Deployment changes

**Finally Phase 4** - Process improvements:
1. 4.2 (Doc fixes) - Quick wins
2. 4.1 (CI/CD) - Infrastructure
3. 4.3 (Observability) - Ongoing improvement

### Per-Phase Checkpoints

Before starting each phase:
- [ ] Review subtasks and estimate effort
- [ ] Identify any blockers or dependencies
- [ ] Communicate plan to stakeholders

After completing each phase:
- [ ] Run verification checklist
- [ ] Update `docs/back-on-track/current.md` with new state
- [ ] Commit changes and tag release

---

## Key Files Reference

**IaC (secrets outputs)**:
- `infra/modules/redis.bicep:91-92`
- `infra/modules/storage.bicep:104`
- `infra/modules/log-analytics.bicep:22`
- `infra/modules/acr.bicep:27`
- `infra/main.bicep` (orchestrator)

**Secret Handling**:
- `gsd-browser/src/gsd_browser/cli.py:44` (`_redact_url_password`)
- `gsd-browser/src/gsd_browser/optionb/task_backend.py:25` (needs fix)

**Artifacts**:
- `gsd-browser/src/gsd_browser/optionb/screenshot_artifacts.py`
- `gsd-browser/src/gsd_browser/optionb/artifact_index.py`
- `gsd-browser/src/gsd_browser/management_api/app.py:571`

**Sessions**:
- `gsd-browser/src/gsd_browser/management_api/app.py:387-498`
- `gsd-browser/src/gsd_browser/optionb/task_ownership.py`
- `gsd-browser/src/gsd_browser/optionb/compat_jobs.py`

**Streaming**:
- `gsd-browser/src/gsd_browser/streaming/server.py:156-167`
- `gsd-browser/src/gsd_browser/streaming/security.py:220-395`
- `gsd-browser/src/gsd_browser/optionb/identity.py:98` (`GsdJwtVerifier` class to reuse)
- `gsd-browser/src/gsd_browser/fastmcp_v2_http.py:49` (env wiring example)
- `gsd-browser/src/gsd_browser/management_api/app.py:133` (env wiring example)

**CI/CD**:
- `infra/scripts/deploy.sh`
- `infra/scripts/build-push.sh`
- `.github/workflows/` (to create)
