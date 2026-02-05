# Azure Cost Analysis

Estimated monthly costs for the GSD platform on Azure. All prices are East US region, pay-as-you-go (Microsoft Azure Sponsorship).

## Production Baseline (1 replica each)

| Resource | SKU | Monthly Est. |
|---|---|---|
| Azure Container Apps — API (1 vCPU, 2 GiB) | Consumption | ~$36 |
| Azure Container Apps — Mgmt (0.5 vCPU, 1 GiB) | Consumption | ~$18 |
| Azure Container Apps — Worker (2 vCPU, 4 GiB) | Consumption | ~$73 |
| Azure Cache for Redis | Standard C2 (6 GB) | ~$162 |
| Blob Storage (Standard LRS) | Hot tier, <10 GB | ~$2 |
| Log Analytics | 5 GB/day ingestion | ~$12 |
| Container Registry | Basic | ~$5 |
| Static Web Apps | Free tier | $0 |
| VNet + Private Endpoints | 2 endpoints | ~$15 |
| **Total (baseline)** | | **~$323/mo** |

## Production at Scale (peak hours)

Assumes autoscaling during business hours: API 3x, Worker 10x, Mgmt 2x.

| Resource | SKU | Monthly Est. |
|---|---|---|
| ACA — API (avg 2 replicas) | 1 vCPU × 2 | ~$72 |
| ACA — Mgmt (avg 1.5 replicas) | 0.5 vCPU × 1.5 | ~$27 |
| ACA — Worker (avg 5 replicas) | 2 vCPU × 5 | ~$365 |
| Redis | Standard C2 | ~$162 |
| Blob Storage | Hot tier, ~50 GB | ~$5 |
| Log Analytics | 15 GB/day | ~$36 |
| ACR | Basic | ~$5 |
| Static Web Apps | Free | $0 |
| VNet + Private Endpoints | 2 endpoints | ~$15 |
| **Total (scaled)** | | **~$687/mo** |

## Development / Staging

Minimal configuration for testing.

| Resource | SKU | Monthly Est. |
|---|---|---|
| ACA — API (0.25 vCPU, 0.5 GiB) | Min scale | ~$9 |
| ACA — Worker (0.5 vCPU, 1 GiB) | Min scale | ~$18 |
| Redis | Basic C0 (250 MB) | ~$16 |
| Blob Storage | Hot, <1 GB | ~$1 |
| Log Analytics | 1 GB/day | ~$3 |
| ACR | Basic | ~$5 |
| **Total (dev)** | | **~$52/mo** |

## Cost Optimization Strategies

1. **Scale-to-zero workers**: ACA supports min replicas = 0 for workers during off-peak. Saves ~60% on worker costs.
2. **Redis downgrade**: Switch to Basic C1 (1 GB) if memory permits. Saves ~$100/mo but loses replication.
3. **Reserved instances**: 1-year reservation on Redis saves ~35%.
4. **Log Analytics**: Reduce retention to 7 days for dev. Use Basic tier for non-critical logs.
5. **Spot containers**: Not yet available for ACA, but monitor for future support.

## External Costs (not Azure)

| Service | Est. Monthly |
|---|---|
| Anthropic API (claude-haiku-4-5) | Usage-based, ~$50-500 |
| Clerk authentication | Free tier up to 10K MAU |
| GitHub Actions | Free tier (2000 min/mo) |

## Sponsorship Budget Notes

The Microsoft Azure Sponsorship provides credits. Monitor spend via:
```bash
az consumption usage list --query "[].{Name:instanceName, Cost:pretaxCost}" -o table
```

Set budget alerts at 50%, 75%, 90% thresholds in Azure Cost Management.
