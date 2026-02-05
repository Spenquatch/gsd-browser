# Current State (prod) — 2026-02-05

This file captures the **current deployed state** of the GSD Browser system in Azure, including
the ad-hoc patches applied to reach a functional end-to-end workflow. The goal is to give a
fresh agent a reliable “ground truth” snapshot to compare against earlier plans/ADRs and then
drive cleanup + hardening work.

## What is working (today)

- **Job queue → worker execution works**: jobs submitted via the MCP API transition
  `queued → running → completed` (or `failed`) and `started_at` is populated.
- **Sessions list works**: the Management API (`/api/v1/sessions`) returns sessions for compat jobs
  and they show up in the dashboard (including terminated sessions until TTL).
- **Screenshots persist and are retrievable**:
  - Worker captures step screenshots and persists them as artifacts (Azure Blob-backed).
  - CLI script can download screenshots by `session_id` (via `get_screenshots`).
  - Mgmt API `/api/v1/sessions/{id}/screenshots` returns screenshot metadata; `include_data=true`
    currently only includes inline base64 for legacy Redis-backed artifacts (dashboard thumbnail support needs follow-up for Azure-backed blobs).

## High-level architecture (prod)

1. **Dashboard (Azure Static Web App)** authenticates via Clerk and calls the **Management API**
   for sessions + artifacts, and calls the **MCP API** for job submission (indirectly, via user tools).
2. **MCP API (`gsd-prod-api`)** accepts MCP JSON-RPC (`/mcp`) and submits long-running jobs into
   **Docket (Redis backend)**.
3. **Worker (`gsd-prod-worker`)** consumes Docket tasks from Redis and executes browser automation
   (Chrome + browser-use via CDP).
4. **Management API (`gsd-prod-mgmt`)** reads session ownership records + task run state from Redis
   and exposes REST endpoints for the dashboard.
5. **Redis** is Azure Cache for Redis (TLS, `rediss://…:6380/0`).

## Azure resources (prod)

Resource Group: `gsd-prod-rg` (East US)

Current prod image tag (CI deploy): `sha-b4ae6d68e936` (GitHub Actions run `21729149468`, deployed 2026-02-05)

Last manual smoke run image tag (Phase 3): `phase3-streaming-1770320691`

### Container Apps

| Component | Name | FQDN | Latest Ready Revision | Image |
|---|---|---|---|---|
| MCP API | `gsd-prod-api` | `https://gsd-prod-api.yellowplant-7a34cb33.eastus.azurecontainerapps.io` | `gsd-prod-api--0000020` | `gsdprodacr.azurecr.io/gsd-browser:sha-b4ae6d68e936` |
| Worker | `gsd-prod-worker` | `https://gsd-prod-worker.yellowplant-7a34cb33.eastus.azurecontainerapps.io` | `gsd-prod-worker--0000015` | `gsdprodacr.azurecr.io/gsd-browser:sha-b4ae6d68e936` |
| Mgmt API | `gsd-prod-mgmt` | `https://gsd-prod-mgmt.yellowplant-7a34cb33.eastus.azurecontainerapps.io` | `gsd-prod-mgmt--0000016` | `gsdprodacr.azurecr.io/gsd-browser:sha-b4ae6d68e936` |

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
- `stream_url` (currently usually `null` in prod unless `GSD_STREAMING_PUBLIC_HOST` is set)

## Artifacts (screenshots)

### Current persistence path (Azure Blob-backed)

Production uses **Azure Blob Storage** via the native SDK (Managed Identity), and supports inline
and/or presigned delivery in tool responses.

Implementation:

- `gsd-browser/src/gsd_browser/optionb/screenshot_artifacts.py`
- `gsd-browser/src/gsd_browser/optionb/artifact_index.py`
- `gsd-browser/src/gsd_browser/optionb/azure_blob_client.py`
- retrieval support in MCP tool: `gsd-browser/src/gsd_browser/mcp_server.py` (`get_screenshots`)
- retrieval support in Mgmt API: `gsd-browser/src/gsd_browser/management_api/app.py`

Validated in Azure:

- In-container artifact smoke (`python -m gsd_browser.optionb.smoke_artifacts --delivery-mode both --cleanup`) succeeded.

### Mgmt API endpoint (for dashboard)

- `GET /api/v1/sessions/{session_id}/screenshots?last_n=10&screenshot_type=agent_step&include_data=true`

Notes:

- `include_data=true` only returns `data_base64` for legacy Redis-backed screenshots.
- This endpoint is intentionally capped (`last_n` max 20) to avoid huge payloads.

### CLI scripts for prod

Scripts live under `gsd-browser/scripts/`:

- `prod_submit_job.sh` (`--json` recommended)
- `prod_job_get.sh`
- `prod_job_wait.sh`
- `prod_get_screenshots.sh <session_id> [last_n] [agent_step|stream_sample]`

## Live streaming (status: not hardened / mostly off)

There are **two different streaming UIs** in the repo:

1. **Legacy static streaming dashboard** served by the streaming server
   (`gsd_browser/streaming/dashboard_static/…`).
2. **React dashboard** (`gsd-dashboard`) which expects `stream_url` and connects to Socket.IO
   namespaces `/stream` and `/ctrl`.

Current production state:

- The worker Container App exposes port `5009`, but the worker process runs a lightweight
  **health server** on that port (not the full streaming server).
- `stream_url` is typically unset in Management API output unless `GSD_STREAMING_PUBLIC_HOST` is set.
- Result: the React dashboard can show sessions + artifacts, but “View Live” is not currently a
  real-time video stream in prod.

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
3. **Mgmt API “Origin required” behavior**: curl without an `Origin` header can return
   `{"error":"origin_not_allowed","origin":""}`. Options:
   - set `GSD_HTTP_ALLOW_NULL_ORIGIN=1` for mgmt, or
   - loosen the hardening policy for server-to-server, or
   - always include an Origin header in tooling/scripts.
4. **Live streaming not production-ready**: currently no reliable externally reachable Socket.IO
   streaming service; worker port 5009 is a health endpoint.
5. **Manual deploy flow**: dashboard requires build-time env vars; backend + frontend releases are
   not pinned/rolled out together via CI/CD.

## Suggested hardening roadmap (next)

1. **Rotate Redis access key** and update the `docket-url` secret on all Container Apps.
2. Replace Redis screenshot blobs with **Azure Blob Storage** uploads (SDK + managed identity or SAS).
3. Decide on live streaming architecture:
   - dedicated `gsd-prod-stream` Container App running `gsd-browser serve-streaming`, or
   - run streaming server inside the worker process (but then health/ingress needs careful design).
4. Add CI/CD:
   - backend: build/push ACR image with immutable tag
   - dashboard: build with publishable key + mgmt base URL and deploy SWA
5. Document env vars in one place and reconcile with `infra/` Bicep + ADRs.
