# Environment Variables (Source of Truth)

This document is the canonical reference for environment variables used by `gsd-browser` (Python).
It is intended for operators (Container Apps/Kubernetes) and for local development.

## Loading order (local / CLI)

1. Process environment
2. `GSD_ENV_FILE` (if set)
3. `.env` (current directory)
4. `~/.gsd/.env` (CLI-friendly default)

## Core

| Variable | Default | Notes |
|---|---:|---|
| `LOG_LEVEL` | `INFO` | Python logging level. |
| `GSD_JSON_LOGS` | `0` | Set to `1` for JSON logs (recommended in containers). |
| `GSD_ENV_FILE` | (unset) | Optional path to an env file (see loading order). |

## LLM provider

| Variable | Default | Notes |
|---|---:|---|
| `GSD_LLM_PROVIDER` | `anthropic` | `anthropic` \| `openai` \| `chatbrowseruse` \| `ollama`. |
| `GSD_MODEL` | `claude-haiku-4-5` | Provider-specific model name. |
| `GSD_FALLBACK_LLM_PROVIDER` | `anthropic` | Optional step-level fallback provider. |
| `GSD_FALLBACK_MODEL` | `claude-sonnet-4-5` | Optional fallback model. |
| `ANTHROPIC_API_KEY` | (unset) | Required when `GSD_LLM_PROVIDER=anthropic` (and for `infra/scripts/deploy.sh`). |
| `OPENAI_API_KEY` | (unset) | Required when `GSD_LLM_PROVIDER=openai`. |
| `BROWSER_USE_API_KEY` | (unset) | Required when `GSD_LLM_PROVIDER=chatbrowseruse`. |
| `BROWSER_USE_LLM_URL` | (unset) | Optional override for Browser Use API base URL. |
| `OLLAMA_HOST` | `http://localhost:11434` | Required when `GSD_LLM_PROVIDER=ollama`. |

## Web-eval budgets (optional overrides)

| Variable | Default | Notes |
|---|---:|---|
| `GSD_WEB_EVAL_BUDGET_S` | (unset) | Total budget (seconds). If unset, browser-use defaults apply. |
| `GSD_WEB_EVAL_MAX_STEPS` | (unset) | Max steps. If unset, browser-use defaults apply. |
| `GSD_WEB_EVAL_STEP_TIMEOUT_S` | (unset) | Per-step timeout (seconds). If unset, browser-use defaults apply. |
| `GSD_USE_VISION` | `auto` | `auto` \| `true` \| `false`. |

## FastMCP / Docket (queue + state)

These are required for production HTTP deployments (API/worker/mgmt).

| Variable | Default | Notes |
|---|---:|---|
| `FASTMCP_DOCKET_NAME` | `fastmcp` | In prod we use `gsd`. |
| `FASTMCP_DOCKET_URL` | (unset) | Redis URL, typically `rediss://:<key>@<host>:6380/0`. |
| `FASTMCP_DOCKET_CONCURRENCY` | `0` | Worker sets `>0` (e.g. `4`). API/mgmt typically keep `0`. |

## Auth: JWT (Clerk)

Both the MCP API and the management API use these values for Bearer-token verification.

| Variable | Default | Notes |
|---|---:|---|
| `GSD_JWT_JWKS_URL` | (unset) | JWKS URL, e.g. `https://<clerk-domain>/.well-known/jwks.json`. |
| `GSD_JWT_ISSUER` | (unset) | Token issuer URL, e.g. `https://<clerk-domain>`. |
| `GSD_JWT_AUDIENCE` | (unset) | Expected audience, e.g. `gsd`. |
| `GSD_JWT_TENANT_ID_CLAIM` | `tenant_id` | Claim name used for tenant scoping. |
| `GSD_JWT_SUBJECT_ID_CLAIM` | `sub` | Claim name used for subject scoping. |

## Auth: Management API keys (optional)

| Variable | Default | Notes |
|---|---:|---|
| `GSD_API_KEYS_FILE` | (unset) | JSON file of API keys for server-to-server access (alternative to JWT). |
| `GSD_ADMIN_MODE` | `0` | Enable `/api/v1/admin/*` endpoints when `1` (still requires `gsd:admin`). |

## Artifacts: Azure Blob (preferred)

When `GSD_AZURE_STORAGE_ACCOUNT` is set, screenshots/artifacts are stored in Azure Blob Storage.

| Variable | Default | Notes |
|---|---:|---|
| `GSD_AZURE_STORAGE_ACCOUNT` | (unset) | Storage account name (required for Azure artifacts). |
| `GSD_AZURE_BLOB_CONTAINER` | `gsd-artifacts` | Container for artifacts. |
| `GSD_AZURE_STORAGE_CONNECTION_STRING` | (unset) | Optional fallback; if unset, uses Managed Identity via `DefaultAzureCredential`. |

## Retention

| Variable | Default | Notes |
|---|---:|---|
| `GSD_DEPLOYMENT_ENV` | `dev` | `dev` \| `prod` (affects retention defaults). |
| `GSD_RETENTION_SECONDS_DEV` | `86400` | Artifact retention for dev (seconds). |
| `GSD_RETENTION_SECONDS_PROD` | `604800` | Artifact retention for prod (seconds). |

## Artifacts: delivery mode (MCP tool responses)

| Variable | Default | Notes |
|---|---:|---|
| `GSD_ARTIFACT_DELIVERY_MODE` | `inline` | `inline` \| `presigned` \| `both`. |
| `GSD_PRESIGNED_URL_TTL_S` | `900` | Presigned URL TTL (seconds) used by `get_screenshots` (max depends on backend). |

## Artifacts: S3-compatible (optional / cleanup)

Some maintenance paths still support S3-compatible storage.

| Variable | Default | Notes |
|---|---:|---|
| `GSD_S3_ENDPOINT_URL` | (unset) | S3 endpoint (must be `http(s)://...`). |
| `GSD_S3_BUCKET` | (unset) | Bucket name. |
| `GSD_S3_REGION` | (unset) | Region string (arbitrary for some providers). |
| `GSD_S3_ACCESS_KEY_ID` | (unset) | Access key. |
| `GSD_S3_SECRET_ACCESS_KEY` | (unset) | Secret key. |
| `GSD_S3_SSE_MODE` | `sse_s3` | `sse_s3` \| `none`. |

## Streaming

| Variable | Default | Notes |
|---|---:|---|
| `STREAMING_MODE` | `cdp` | `cdp` \| `screenshot`. |
| `STREAMING_QUALITY` | `med` | `low` \| `med` \| `high`. |
| `GSD_STREAMING_AUTH_MODE` | `hmac` | `hmac` (dev) \| `jwt` (prod). |
| `GSD_STREAMING_BIND_HOST` | `127.0.0.1` | Bind host (local). |
| `GSD_STREAMING_PUBLIC_HOST` | (unset) | Public host used to compute `stream_url` in session payloads. |
| `GSD_STREAMING_PUBLIC_SCHEME` | `wss` | `wss` \| `ws`. |
| `GSD_AUTO_PAUSE_ON_TAKE_CONTROL` | `1` | Pause agent when user takes control (dashboard). |

## Worker diagnostics

| Variable | Default | Notes |
|---|---:|---|
| `GSD_WORKER_DIAGNOSTICS_INTERVAL_S` | `0` | If `>0`, worker logs periodic Docket depth diagnostics. |

## HTTP hardening

| Variable | Default | Notes |
|---|---:|---|
| `GSD_HTTP_ALLOWED_ORIGINS` | (unset) | Comma-separated allowlist for `Origin` header validation. |
| `GSD_HTTP_ALLOW_NULL_ORIGIN` | `0` | If `1`, allows requests without an `Origin` header (useful for server-to-server). |

## Dashboard (Vite build-time)

These are consumed by the `gsd-dashboard` build (GitHub Actions usually injects them).

| Variable | Default | Notes |
|---|---:|---|
| `VITE_CLERK_PUBLISHABLE_KEY` | (unset) | Required for the dashboard to initialize Clerk. |
| `VITE_GSD_API_BASE_URL` | (unset) | Base URL for the management API (dashboard calls mgmt, not `/mcp`). |
| `VITE_GSD_CLERK_JWT_TEMPLATE` | `gsd` | Clerk template name passed to `getToken({ template })`. |
