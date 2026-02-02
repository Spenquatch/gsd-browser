# ADR-0025: Azure Reference Deployment

## Status
Proposed

## Context
GSD needs a reference cloud deployment for multi-tenant SaaS operation supporting 5-20 concurrent browser automation sessions. Requirements:
- Container-based compute with autoscaling
- Managed Redis for task state, artifact metadata, and pub/sub
- Object storage for screenshots and artifacts (existing `S3Client` interface)
- Static asset hosting for React dashboard (CDN, custom domains, SSL)
- WebSocket support for real-time frame streaming
- VNet isolation for backend services

Azure was selected as the primary cloud provider. Three compute options were evaluated:
1. **Azure Container Apps (ACA)** — managed containers with built-in autoscaling and Envoy proxy
2. **Azure Kubernetes Service (AKS)** — full Kubernetes with maximum flexibility
3. **Azure Container Instances (ACI)** — simple container hosting, no orchestration

## Decision

### Azure Container Apps (ACA) as the compute platform

**Rationale**: ACA provides the right abstraction level for 5-20 sessions. It includes built-in Envoy proxy with WebSocket support and session affinity, autoscaling based on HTTP concurrency or custom metrics, and managed TLS. AKS adds operational overhead (cluster management, node pools) not justified at this scale. ACI lacks orchestration and autoscaling.

### 1) Compute: Azure Container Apps

**MCP Server / Browser Worker** — single container app with scaling:
- Container image: `gsd-browser` with browser dependencies (Playwright + Chromium)
- Min replicas: 1, Max replicas: 20
- Scale rule: HTTP concurrency (1 session per replica) or KEDA Redis queue length
- Resources per replica: 2 vCPU, 4 GiB RAM (browser automation is memory-intensive)
- Ingress: External, WebSocket upgrade enabled, session affinity enabled

**Container App Environment**:
- Single ACA environment in a VNet
- Internal DNS for service-to-service communication
- Managed identity for accessing Azure services (Redis, Blob Storage)

### 2) Redis: Azure Cache for Redis

- **SKU**: Basic C1 (1 GiB) for dev, Standard C2 (6 GiB) for production
- **Access**: Private endpoint in VNet (no public access)
- **TLS**: Enabled (Azure default)
- **Usage**: Task ownership records, job state (FastMCP Docket), session metadata
- **Connection**: Via `REDIS_URL` env var (existing `GSD_REDIS_URL` config)

### 3) Storage: Azure Blob Storage with S3-compatible endpoint

- **Account type**: General-purpose v2, Hot tier
- **Access**: Private endpoint in VNet
- **S3 compatibility**: Azure Blob Storage supports S3-compatible API via the Blob REST API
- **Container**: `gsd-artifacts` for screenshots, recordings, and task artifacts
- **Authentication**: Managed identity (preferred) or access key (fallback)
- **Connection**: Existing `S3Client` interface with Azure Blob S3-compat endpoint URL

**Fallback plan**: If S3-compat proves insufficient (e.g., presigned URL edge cases), use `azure-storage-blob` SDK with a thin adapter implementing the same `ArtifactStore` interface.

### 4) Frontend: Azure Static Web Apps

- **Source**: `gsd-dashboard/` Vite build output (`dist/`)
- **Features**: Global CDN, custom domains, automatic SSL, GitHub Actions integration
- **Auth**: Clerk handles auth client-side; Static Web Apps serves pure static files
- **Routing**: SPA fallback (all routes → `index.html`)
- **Environment**: Staging + Production slots

### 5) Networking: VNet with private endpoints

```
┌─────────────────── VNet (10.0.0.0/16) ───────────────────┐
│                                                            │
│  ┌─── ACA Subnet (10.0.0.0/23) ──┐                       │
│  │  ACA Environment               │                       │
│  │  ├── gsd-worker (1-20 replicas)│                       │
│  │  └── Envoy Proxy (built-in)    │                       │
│  └────────────────────────────────┘                       │
│                                                            │
│  ┌─── Private Endpoints Subnet (10.0.2.0/24) ──┐         │
│  │  ├── Redis Private Endpoint                   │         │
│  │  └── Blob Storage Private Endpoint            │         │
│  └──────────────────────────────────────────────┘         │
│                                                            │
└────────────────────────────────────────────────────────────┘

External:
  ├── ACA Public Ingress (HTTPS + WSS)
  ├── Azure Static Web Apps (Dashboard CDN)
  └── Clerk (Identity Provider, external SaaS)
```

### 6) No separate Application Gateway
ACA's built-in Envoy proxy handles:
- TLS termination
- WebSocket upgrade
- Session affinity (cookie or header-based)
- Health check routing

A separate Azure Application Gateway is unnecessary at this scale and adds cost + complexity.

## Consequences

### Positive
- Managed compute with autoscaling — no cluster management overhead
- Built-in WebSocket and session affinity support
- Private networking for Redis and storage — defense in depth
- Static Web Apps provides global CDN for dashboard with zero infra management
- Managed identity eliminates credential rotation for Azure services

### Negative / Costs
- ACA has less flexibility than AKS for custom networking/scheduling
- Azure Blob S3-compat may have edge cases requiring fallback to native SDK
- ACA Envoy idle timeout (default 4 minutes) may need tuning for long WebSocket sessions
- Single-region initially — multi-region requires additional architecture

## Implementation Notes

### Infrastructure as Code
Use Bicep templates (Azure-native IaC) for:
- VNet and subnet definitions
- ACA environment and container app
- Redis Cache with private endpoint
- Blob Storage account with private endpoint
- Static Web Apps resource

Terraform is an alternative for teams with existing Terraform workflows.

### Environment variable mapping for ACA
```env
# Redis
GSD_REDIS_URL=rediss://<redis-name>.redis.cache.windows.net:6380

# Blob Storage (S3-compat)
GSD_S3_ENDPOINT_URL=https://<storage-account>.blob.core.windows.net
GSD_S3_BUCKET=gsd-artifacts
GSD_S3_ACCESS_KEY_ID=<storage-account-name>
GSD_S3_SECRET_ACCESS_KEY=<storage-account-key>

# Streaming
GSD_STREAMING_BIND_HOST=0.0.0.0
GSD_STREAMING_PUBLIC_HOST=gsd.example.com
GSD_STREAMING_PUBLIC_SCHEME=wss
GSD_STREAMING_AUTH_MODE=jwt

# JWT (Clerk)
GSD_JWT_ISSUER=https://<clerk-domain>
GSD_JWT_JWKS_URI=https://<clerk-domain>/.well-known/jwks.json
GSD_JWT_AUDIENCE=gsd

# LLM
GSD_LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=<from-key-vault>

# Concurrency
GSD_MAX_SESSIONS_PER_TENANT=5
```

### GitHub Actions CI/CD pipeline
1. On push to `main`:
   - Build container image → push to Azure Container Registry (ACR)
   - Update ACA container app revision
   - Build React dashboard → deploy to Static Web Apps
2. On PR: build + test only (no deploy)

### Cost estimate (5-20 concurrent sessions)

| Service | Configuration | Est. Monthly Cost |
|---------|--------------|-------------------|
| ACA | 5 replicas avg × 2 vCPU × 4 GiB | ~$150-300 |
| Redis | Standard C2 (6 GiB) | ~$160 |
| Blob Storage | Hot tier, <100 GiB | ~$5 |
| Static Web Apps | Standard tier | ~$9 |
| ACR | Basic tier | ~$5 |
| VNet / Private Endpoints | 2 endpoints | ~$15 |
| **Total** | | **~$350-500/mo** |

Costs scale linearly with replica count. At 20 concurrent sessions: ~$600-900/mo.

## Open Questions
None (decisions pinned).

## References
- `docs/adr/ADR-0009-distributed-artifact-storage-for-scaled-tasks.md`
- `docs/adr/ADR-0015-option-b-operational-topology-and-reference-deployment.md`
- `docs/adr/ADR-0024-remote-streaming-architecture.md`
- Azure Container Apps documentation
- Azure Cache for Redis pricing
- Azure Blob Storage S3-compatible API
