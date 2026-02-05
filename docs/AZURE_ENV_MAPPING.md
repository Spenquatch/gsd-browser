# Azure Environment Variable Mapping

Maps Docker Compose environment variables to their Azure Container Apps equivalents.

## API Server (port 8080)

| Compose Variable | Azure Source | ACA Value |
|---|---|---|
| `GSD_DEPLOYMENT_ENV` | Hardcoded | `prod` |
| `GSD_TRANSPORT` | Hardcoded | `http` |
| `FASTMCP_DOCKET_URL` | Redis module output → ACA secret | `rediss://:KEY@HOST:6380/0` |
| `FASTMCP_DOCKET_NAME` | Hardcoded | `gsd` |
| `FASTMCP_DOCKET_CONCURRENCY` | Hardcoded | `0` (HTTP server, no task execution) |
| `GSD_JWT_JWKS_URL` | Bicep parameter | `https://fresh-sheepdog-88.clerk.accounts.dev/.well-known/jwks.json` |
| `GSD_JWT_ISSUER` | Bicep parameter | `https://fresh-sheepdog-88.clerk.accounts.dev` |
| `GSD_JWT_AUDIENCE` | Bicep parameter | `gsd` |
| `GSD_JWT_TENANT_ID_CLAIM` | Hardcoded | `tenant_id` |
| `GSD_JWT_SUBJECT_ID_CLAIM` | Hardcoded | `sub` |
| `ANTHROPIC_API_KEY` | GitHub Secret → ACA secret | (sensitive) |
| `GSD_LLM_PROVIDER` | Hardcoded | `anthropic` |
| `GSD_MODEL` | Hardcoded | `claude-haiku-4-5` |

## Management API (port 8081)

| Compose Variable | Azure Source | ACA Value |
|---|---|---|
| `GSD_DEPLOYMENT_ENV` | Hardcoded | `prod` |
| `FASTMCP_DOCKET_URL` | Redis module output → ACA secret | `rediss://:KEY@HOST:6380/0` |
| `FASTMCP_DOCKET_NAME` | Hardcoded | `gsd` |
| `GSD_JWT_JWKS_URL` | Bicep parameter | Clerk JWKS URL |
| `GSD_JWT_ISSUER` | Bicep parameter | Clerk issuer |
| `GSD_JWT_AUDIENCE` | Bicep parameter | `gsd` |
| `GSD_JWT_TENANT_ID_CLAIM` | Hardcoded | `tenant_id` |
| `GSD_JWT_SUBJECT_ID_CLAIM` | Hardcoded | `sub` |

> **Note:** Management API does not use `GSD_API_KEYS_FILE` in Azure. API key auth is handled by Clerk JWT only.

## Worker (port 5009)

| Compose Variable | Azure Source | ACA Value |
|---|---|---|
| `GSD_DEPLOYMENT_ENV` | Hardcoded | `prod` |
| `GSD_USE_FASTMCP_V2` | Hardcoded | `true` |
| `FASTMCP_DOCKET_URL` | Redis module output → ACA secret | `rediss://:KEY@HOST:6380/0` |
| `FASTMCP_DOCKET_NAME` | Hardcoded | `gsd` |
| `FASTMCP_DOCKET_CONCURRENCY` | Hardcoded | `4` |
| `GSD_S3_ENDPOINT_URL` | Storage module output | `https://<account>.blob.core.windows.net/` |
| `GSD_S3_BUCKET` | Hardcoded | `gsd-artifacts` |
| `GSD_S3_REGION` | Hardcoded | `us-east-1` (unused by Azure Blob) |
| `GSD_S3_ACCESS_KEY_ID` | Storage module output | Storage account name |
| `GSD_S3_SECRET_ACCESS_KEY` | Storage module output → ACA secret | Storage account key |
| `GSD_S3_SSE_MODE` | Hardcoded | `none` |
| `GSD_ARTIFACT_DELIVERY_MODE` | Hardcoded | `both` |
| `GSD_PRESIGNED_URL_TTL_S` | Hardcoded | `900` |
| `ANTHROPIC_API_KEY` | GitHub Secret → ACA secret | (sensitive) |
| `GSD_LLM_PROVIDER` | Hardcoded | `anthropic` |
| `GSD_MODEL` | Hardcoded | `claude-haiku-4-5` |

## Secrets Strategy

All secrets use **ACA native secrets** (not Azure Key Vault) for simplicity:

| Secret | Source | Injected Via |
|---|---|---|
| `ANTHROPIC_API_KEY` | `@secure()` Bicep param → GitHub Secret | ACA secret ref |
| `FASTMCP_DOCKET_URL` | Constructed from Redis module outputs | ACA secret ref |
| `GSD_S3_SECRET_ACCESS_KEY` | Storage module `listKeys()` output | ACA secret ref |
| ACR password | ACR module `listCredentials()` output | ACA registry config |

## Key Differences from Docker Compose

1. **Redis**: Compose uses `redis://valkey:6379/0` (plaintext). Azure uses `rediss://:KEY@HOST:6380/0` (TLS on 6380).
2. **Storage**: Compose uses SeaweedFS S3 API. Azure uses Blob Storage endpoint. If boto3 S3 compatibility fails, an `azure-storage-blob` adapter may be needed.
3. **Networking**: Compose uses Docker bridge networking. Azure uses VNet with private endpoints for Redis and Storage.
4. **Auth**: Compose supports file-based API keys (`GSD_API_KEYS_FILE`). Azure uses Clerk JWT exclusively.
