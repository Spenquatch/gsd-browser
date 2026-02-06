# Current State (prod) — 2026-02-06 (truth pass)

This file captures the **current deployed state** of the GSD Browser system in Azure, including
the ad-hoc patches applied to reach a functional end-to-end workflow. The goal is to give a
fresh agent a reliable “ground truth” snapshot to compare against earlier plans/ADRs and then
drive cleanup + hardening work.

Notes on this snapshot:

- “Prod” specifics (resource names, image tags) reflect the most recent observed deploy noted in
  this doc (2026-02-05).
- Behavior statements in the focus areas below were cross-checked against **in-repo code + infra**
  on 2026-02-06 (this truth pass).

## What is working (today)

- **Job queue → worker execution works**: jobs submitted via the MCP API transition
  `queued → running → completed` (or `failed`) and `started_at` is populated.
- **Sessions list works**: the Management API (`/api/v1/sessions`) returns sessions for compat jobs
  and they show up in the dashboard (including terminated sessions until TTL).
- **Screenshots persist and are retrievable**:
  - Worker captures step screenshots and persists them as artifacts (Azure Blob-backed in prod; S3/Redis supported).
  - CLI script can download screenshots by `session_id` (via `get_screenshots`).
  - Mgmt API `/api/v1/sessions/{id}/screenshots` returns screenshot metadata; `include_data=true`
    currently only includes inline base64 for legacy Redis-backed artifacts (dashboard thumbnail support needs follow-up for Azure-backed blobs).

## High-level architecture (prod)

1. **Dashboard (Azure Static Web App)** authenticates via Clerk and calls the **Management API**
   for sessions + artifacts, and calls the **MCP API** for job submission (indirectly, via user tools).
2. **MCP API (`gsd-prod-api`)** accepts MCP JSON-RPC (`/mcp`) and submits long-running jobs into
   **Docket (Redis backend)**.
3. **Worker (`gsd-prod-worker`)** consumes Docket tasks from Redis and executes browser automation
   (Chrome + browser-use via CDP). The worker process also runs the streaming + health ASGI server
   on the worker ingress port (default `5009`; see “Live streaming” below).
4. **Management API (`gsd-prod-mgmt`)** reads session ownership records + task run state from Redis
   and exposes REST endpoints for the dashboard.
5. **Redis** is Azure Cache for Redis (TLS, `rediss://…:6380/0`).

## Azure resources (prod)

Resource Group: `gsd-prod-rg` (East US)

Current prod image tag (CI deploy): `sha-dd3e52ec0a64` (GitHub Actions run `21766264656`, deployed 2026-02-06; built via `backend-build.yml` run `21766199096`)

Last manual smoke run image tag (Phase 3): `phase3-streaming-1770320691`

### Container Apps

| Component | Name | FQDN | Latest Ready Revision | Image |
|---|---|---|---|---|
| MCP API | `gsd-prod-api` | `https://gsd-prod-api.yellowplant-7a34cb33.eastus.azurecontainerapps.io` | `gsd-prod-api--0000021` | `gsdprodacr.azurecr.io/gsd-browser:sha-dd3e52ec0a64` |
| Worker | `gsd-prod-worker` | `https://gsd-prod-worker.yellowplant-7a34cb33.eastus.azurecontainerapps.io` | `gsd-prod-worker--0000016` | `gsdprodacr.azurecr.io/gsd-browser:sha-dd3e52ec0a64` |
| Mgmt API | `gsd-prod-mgmt` | `https://gsd-prod-mgmt.yellowplant-7a34cb33.eastus.azurecontainerapps.io` | `gsd-prod-mgmt--0000017` | `gsdprodacr.azurecr.io/gsd-browser:sha-dd3e52ec0a64` |

### Smoke checks (passed)

HTTP health:

```bash
curl -sS "https://gsd-prod-api.yellowplant-7a34cb33.eastus.azurecontainerapps.io/.well-known/oauth-protected-resource"
curl -sS -i "https://gsd-prod-mgmt.yellowplant-7a34cb33.eastus.azurecontainerapps.io/healthz"
curl -sS -i "https://gsd-prod-worker.yellowplant-7a34cb33.eastus.azurecontainerapps.io/healthz/worker"
```

In-container artifact smoke (Azure Blob + Managed Identity + `get_screenshots`):

```bash
az containerapp exec -g gsd-prod-rg -n gsd-prod-worker --command \
  "python -m gsd_browser.optionb.smoke_artifacts --delivery-mode both --cleanup"
```

Mgmt metrics endpoint (intentionally requires auth):

```bash
curl -sS -i "https://gsd-prod-mgmt.yellowplant-7a34cb33.eastus.azurecontainerapps.io/metrics"
```

### Static Web App (dashboard)

- Name: `gsd-prod-dashboard`
- Default hostname: `https://zealous-wave-0ed3a980f.1.azurestaticapps.net`
- Custom domain: `https://browse.buildconnectors.com` (expected)

## Auth (Clerk)

### Backend JWT verification (Mgmt + API)

Configured on `gsd-prod-mgmt` (and similarly on the MCP API) via:

- `GSD_JWT_JWKS_URL=https://clerk.browse.buildconnectors.com/.well-known/jwks.json`
- `GSD_JWT_ISSUER=https://clerk.browse.buildconnectors.com`
- `GSD_JWT_AUDIENCE=gsd`
- `GSD_JWT_TENANT_ID_CLAIM=tenant_id`
- `GSD_JWT_SUBJECT_ID_CLAIM=sub`

Mgmt `/metrics` additionally requires JWT scope: `gsd:admin` (and rejects API keys).

### Frontend (dashboard)

The Vite build embeds Clerk config at build time:

- `VITE_CLERK_PUBLISHABLE_KEY=pk_live_…`
- `VITE_GSD_API_BASE_URL=https://gsd-prod-mgmt…` (dashboard calls Mgmt API, not MCP API)
- `VITE_GSD_CLERK_JWT_TEMPLATE=gsd` (template name for `getToken({ template })`)

Important: **Static Web Apps appsettings are not used** for Vite runtime config. If the publishable
key is missing at build time, the dashboard will not be able to initialize Clerk.

To avoid a white-screen crash, `gsd-dashboard/src/main.tsx` now renders a clear “misconfigured”
page if `VITE_CLERK_PUBLISHABLE_KEY` is absent.

## Docket / Redis (queue)

Both API and Worker use:

- `FASTMCP_DOCKET_NAME=gsd`
- `FASTMCP_DOCKET_URL` via Container App secret `docket-url` (TLS `rediss://…`)
- `FASTMCP_DOCKET_CONCURRENCY=4` on the worker

### Redis 6.0 compatibility patch (XAUTOCLAIM)

Azure Cache for Redis was observed to behave like Redis 6.0 for `XAUTOCLAIM`. Docket >= 0.16 uses
`XAUTOCLAIM` for redelivery; when unsupported, the worker could silently stop processing.

We apply a compatibility patch at worker startup:

- `gsd-browser/src/gsd_browser/optionb/docket_redis_compat.py`
- wired in `gsd-browser/src/gsd_browser/cli.py` (`gsd-browser worker`)

## Sessions (dashboard list)

### Why sessions were previously “missing”

The dashboard polls `GET /api/v1/sessions` from the Management API. That endpoint lists sessions
based on **TaskOwnershipRecord** keys in Redis:

- key pattern: `gsd:v1:tasks:*:owner`
- model: `gsd-browser/src/gsd_browser/optionb/task_ownership.py`
- listing logic: `gsd-browser/src/gsd_browser/management_api/app.py`

Compat jobs (`web_eval_agent_submit`, etc.) originally did not persist TaskOwnershipRecords, so
Mgmt returned an empty list and the dashboard showed nothing.

### Current behavior

Compat job submission now persists TaskOwnershipRecords best-effort:

- `gsd-browser/src/gsd_browser/optionb/compat_jobs.py` (`submit_job()`)

Mgmt sessions payload includes:

- `session_id`
- `status` (`create`, `active`, `terminated`) derived from the Docket runs hash state
- `created_at`, `last_activity_at`
- `stream_url` (derived from `GSD_STREAMING_PUBLIC_HOST`/`GSD_STREAMING_PUBLIC_SCHEME`; in prod
  IaC it is set to the worker FQDN, so `stream_url` should typically be a non-null base URL like
  `https://<prefix>-worker.<aca-env-domain>`)

## Artifacts (screenshots)

### Storage backend (what the code does)

Screenshots always get an **index record in Redis** (per-identity session ZSET + per-artifact meta
key). The image bytes are stored in one of three backends, selected in this order:

- **Azure Blob (preferred)** when `GSD_AZURE_STORAGE_ACCOUNT` is set.
- **S3-compatible** when a full S3 config is present (`GSD_S3_*`).
- **Redis fallback** otherwise (stores raw bytes under a Redis key with a TTL).

In prod IaC (`infra/modules/aca-app-worker.bicep`), both Azure and S3 env vars are set, but the
code will choose **Azure Blob** because `GSD_AZURE_STORAGE_ACCOUNT` is present.

Implementation pointers:

- persistence + backend selection: `gsd-browser/src/gsd_browser/optionb/screenshot_artifacts.py`
- Redis index format + cleanup runner: `gsd-browser/src/gsd_browser/optionb/artifact_index.py`
- Azure client (Managed Identity or connection string): `gsd-browser/src/gsd_browser/optionb/azure_blob_client.py`

### Presigned URLs (Azure SAS via Managed Identity)

`gsd_browser.optionb.azure_blob_client.AzureBlobClient.generate_sas_url()` generates **User Delegation SAS** tokens via `BlobServiceClient.get_user_delegation_key()` (Managed Identity / AAD token).

RBAC requirement: the calling Container App’s system-assigned identity must have **Storage Blob Data Contributor** on the storage account (this role includes `generateUserDelegationKey`).

As of **2026-02-06** (checked via Azure CLI):

- `gsd-prod-api` and `gsd-prod-worker` both have **Storage Blob Data Contributor** on storage account `gsdprodstore`.
- `gsd-prod-mgmt` currently has **no managed identity** (`identity.type == None`), and does not receive `GSD_AZURE_STORAGE_ACCOUNT` / `GSD_AZURE_BLOB_CONTAINER` env vars via IaC, so `/api/v1/sessions/{id}/screenshots` cannot reliably return signed Azure Blob URLs until mgmt is updated/redeployed.

### Mgmt API endpoint (for dashboard)

- `GET /api/v1/sessions/{session_id}/screenshots?last_n=10&screenshot_type=agent_step&include_data=true`

Notes:

- `include_data=true` only returns `data_base64` for legacy Redis-backed screenshots.
- For Azure Blob- and S3-backed screenshots, the endpoint returns a short-lived signed URL in `url`
  (and also includes `page_url` + `url_expires_at`).
- This endpoint is intentionally capped (`last_n` max 20) to avoid huge payloads.

### MCP tool delivery behavior (`get_screenshots`)

The MCP tool supports three delivery modes controlled by `GSD_ARTIFACT_DELIVERY_MODE`:

- `inline` (default): returns images inline (base64) in the MCP response.
- `presigned`: returns presigned URLs only (no inline images).
- `both`: returns inline images and presigned URLs.

In HTTP/Option B (prod), `get_screenshots` prefers distributed artifacts via the Redis index and
can retrieve bytes from Azure/S3 for inline mode and issue SAS/presigned URLs for URL mode.

### Retention + cleanup (what the code does today)

Retention is driven by:

- `GSD_RETENTION_SECONDS_PROD` / `GSD_RETENTION_SECONDS_DEV` (defaults: 7 days prod, 1 day dev).

What’s enforced automatically:

- Redis **index keys** (artifact meta + session ZSET membership) expire at `created_at + retention`.
- Redis **blob fallback** keys also get an expiry at `created_at + retention`.

Best-effort deletion:

- The worker runs a periodic cleanup loop (distributed lock) that scans artifact meta keys and
  attempts to delete the underlying blob for expired artifacts and for orphaned “pending” uploads.
- In the current worker entrypoint, the cleanup runner is wired to a **S3 delete function** (it
  requires `GSD_S3_*` to be set). If artifacts are stored via the native Azure SDK, blob deletion
  depends on whether the S3 configuration points at the same backing store (S3-compatible) or on
  an external lifecycle policy.

If a hard retention guarantee is required for Azure Blob bytes, we need an explicit decision:

- implement Azure deletion in the cleanup runner (call `AzureBlobClient.delete()`), and/or
- enforce retention via Azure Storage lifecycle management on the container.

### CLI scripts for prod

Scripts live under `gsd-browser/scripts/`:

- `prod_submit_job.sh` (`--json` recommended)
- `prod_job_get.sh`
- `prod_job_wait.sh`
- `prod_get_screenshots.sh <session_id> [last_n] [agent_step|stream_sample]`

## Live streaming (deployed; needs hardening)

There are **two different streaming UIs** in the repo:

1. **Legacy static streaming dashboard** served by the streaming server
   (`gsd_browser/streaming/dashboard_static/…`).
2. **React dashboard** (`gsd-dashboard`) which expects `stream_url` and connects to Socket.IO
   namespaces `/stream` and `/ctrl`.

Current production state:

- The worker process **attempts to start the full streaming server** (FastAPI + Socket.IO +
  legacy static dashboard) on the worker ingress port (default `5009` via `PORT`/`GSD_WORKER_HEALTH_PORT`).
- If the streaming server fails to start, the worker falls back to a minimal HTTP server that
  responds `ok` (so the container stays live even if streaming is broken).
- In prod IaC, both the Management API and MCP API are configured to advertise the worker as the
  streaming base URL via `GSD_STREAMING_PUBLIC_HOST`/`GSD_STREAMING_PUBLIC_SCHEME`.
- In prod IaC, streaming auth mode is `jwt` (`GSD_STREAMING_AUTH_MODE=jwt`), so:
  - `/healthz` is public and returns JSON including `streaming_mode`.
  - the legacy static dashboard (`/` and `/dashboard`) requires a JWT (Authorization header or
    `?token=...` query param).
  - Socket.IO namespaces `/stream` and `/ctrl` require Socket.IO `auth: { token: <jwt> }`.

Practical check from outside the cluster:

- `curl -sS "https://<worker-fqdn>/healthz"` should return JSON with `status: ok` and
  `streaming_mode` when the streaming ASGI app is running; plain `ok` suggests the fallback health
  server is running instead.

## Operational runbooks

### Build + push backend image (manual)

From repo root:

```bash
TAG="phase3-streaming-$(date +%s)"
IMAGE_TAG="$TAG" ACR_NAME=gsdprodacr RESOURCE_GROUP=gsd-prod-rg ./infra/scripts/build-push.sh
IMAGE_TAG="$TAG" ./infra/scripts/deploy.sh
```

Preferred: use GitHub Actions (`.github/workflows/backend-build.yml`, `.github/workflows/deploy-prod.yml`).

### Build + deploy dashboard (manual)

From repo root:

```bash
cd gsd-dashboard
npm install

export VITE_CLERK_PUBLISHABLE_KEY="pk_live_..."
export VITE_GSD_API_BASE_URL="https://gsd-prod-mgmt.yellowplant-7a34cb33.eastus.azurecontainerapps.io"
export VITE_GSD_CLERK_JWT_TEMPLATE="gsd"

npm run build

SWA_CLI_DEPLOYMENT_TOKEN="$(az staticwebapp secrets list -n gsd-prod-dashboard -g gsd-prod-rg --query properties.apiKey -o tsv)"
npx -y @azure/static-web-apps-cli deploy ./dist --env production
```

## Known issues / weak spots (to harden)

1. **Secrets leaked in old logs**: an older worker revision printed the full Redis URL including
   password. This is now redacted, but the secret should still be rotated.
2. **Queue/worker observability**: add metrics + alerts for backlog age and worker failures.
3. **HTTP hardening gotchas**: API + Mgmt apply an Origin/Host allowlist (ADR-0014). In prod IaC
   we set `GSD_HTTP_ALLOW_NULL_ORIGIN=true` to keep CLI/scripts workable; if you see
   `origin_not_allowed`, check those env vars first.
4. **Streaming is deployed but not “finished”**: the worker runs the streaming server on port 5009,
   but we still need operational hardening (alerts, auth/UX polish, and clarity on whether this
   should stay co-located with the worker or move to a dedicated app).
5. **Manual deploy flow**: dashboard requires build-time env vars; backend + frontend releases are
   not pinned/rolled out together via CI/CD.

## Suggested hardening roadmap (next)

1. **Rotate Redis access key** and update the `docket-url` secret on all Container Apps.
2. **Make retention real for blob bytes**: decide between Azure lifecycle policy vs implementing
   Azure deletes in the cleanup runner (and validate that “S3-compatible” delete config actually
   deletes the same objects we upload via the Azure SDK).
3. Decide on live streaming architecture:
   - keep streaming co-located in the worker (current code + IaC), or
   - split out a dedicated `gsd-prod-stream` Container App (ops isolation, independent scaling).
4. Add CI/CD:
   - backend: build/push ACR image with immutable tag
   - dashboard: build with publishable key + mgmt base URL and deploy SWA
5. Document env vars in one place and reconcile with `infra/` Bicep + ADRs.
