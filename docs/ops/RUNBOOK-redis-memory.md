# Redis Memory Pressure Runbook

This runbook covers handling Redis memory pressure in the GSD production environment.

## Overview

GSD production Redis uses `noeviction` memory policy, meaning Redis will reject writes
when memory is full rather than evicting keys. This ensures data integrity but requires
proactive memory management.

## Alert Thresholds

| Alert | Threshold | Severity | Action |
|-------|-----------|----------|--------|
| `gsd-prod-redis-high-memory` | >80% used | 2 (Warning) | Investigate, plan cleanup |

## Monitoring Commands

### Check Current Memory Usage

```bash
# Via Azure Monitor metrics (preferred for historical data)
az monitor metrics list \
  --resource "/subscriptions/{sub}/resourceGroups/gsd-prod-rg/providers/Microsoft.Cache/Redis/gsd-prod-redis" \
  --metric "usedmemory,usedmemorypercentage" \
  --interval PT1H \
  --output table

# Via Redis INFO command (requires redis-cli access)
# Note: Use SCAN, never KEYS in production!
az redis console -n gsd-prod-redis -g gsd-prod-rg
> INFO memory
```

### Key Distribution Analysis

**IMPORTANT**: Never use the `KEYS` command in production - it blocks Redis.
Use `SCAN` instead:

```bash
# Connect to Redis console
az redis console -n gsd-prod-redis -g gsd-prod-rg

# Count artifact blob keys (sample first 1000)
> SCAN 0 MATCH "gsd:v1:artifacts:*:blob" COUNT 1000

# Count task ownership keys
> SCAN 0 MATCH "gsd:v1:tasks:*:owner" COUNT 1000

# Count session keys
> SCAN 0 MATCH "gsd:v1:sessions:*" COUNT 1000
```

### Identify Large Keys

```bash
# Get memory usage of specific keys (Redis 4.0+)
> MEMORY USAGE "gsd:v1:artifacts:{artifact_id}:blob"

# Sample large keys using DEBUG OBJECT (shows serialized length)
> DEBUG OBJECT "gsd:v1:artifacts:{artifact_id}:blob"
```

## Common Causes

### 1. Screenshot Artifact Accumulation

If artifact storage is misconfigured or unavailable, screenshots can fall back to Redis.
Each screenshot is ~50-200KB, quickly consuming memory.

**Symptoms**:
- Many keys matching `gsd:v1:artifacts:*:blob`
- Worker logs showing `s3_endpoint_incompatible_falling_back_to_redis` or other artifact persistence errors

**Resolution**:
1. Fix Azure Blob storage configuration (preferred: `GSD_AZURE_STORAGE_ACCOUNT` + managed identity)
2. Clean up stale blob keys (see Cleanup section)
3. After fix: verify new screenshots go to Blob storage (and Redis blob keys stop increasing)

### 2. Stale Task/Session Data

Task ownership records and session data should auto-expire, but leaks can occur.

**Symptoms**:
- Many old keys matching `gsd:v1:tasks:*:owner`
- Keys older than `GSD_RETENTION_SECONDS_PROD` (default: 604800 = 7 days)

**Resolution**:
1. Verify expiry is being set on new records
2. Manual cleanup of old records (see Cleanup section)

### 3. Docket Stream Growth

The Docket task queue uses Redis streams which can grow unbounded.

**Symptoms**:
- Large memory usage in `XINFO GROUPS` output
- Pending entries not being acknowledged

**Resolution**:
1. Check worker health - are workers processing tasks?
2. Check for stuck consumers in pending list
3. Trim old entries: `XTRIM gsd:queue MAXLEN ~ 10000`

## Alert Drill Checklist

Use this checklist to verify the alert pipeline works end-to-end:

1. **Acknowledge**: Confirm alert email arrives at `gsd-prod-alerts-ag` receivers.
2. **Triage**: Open Azure Portal > Monitor > Alerts; find the fired `gsd-prod-redis-high-memory` alert.
3. **First graph**: Azure Portal > Redis > Overview > Memory Usage graph.
   ```bash
   SUB_ID=$(az account show --query id -o tsv)
   az monitor metrics list \
     --resource "/subscriptions/${SUB_ID}/resourceGroups/gsd-prod-rg/providers/Microsoft.Cache/Redis/gsd-prod-redis" \
     --metric "usedmemorypercentage" \
     --interval PT1H \
     --output table
   ```
4. **Correlate**: Check if artifact blobs are falling back to Redis:
   ```bash
   az containerapp logs show -n gsd-prod-worker -g gsd-prod-rg --tail 200 2>&1 | grep -i "redis.*fallback\|blob.*fail"
   ```
5. **Resolve or escalate**: If memory is stable/decreasing, resolve. If growing, follow cleanup procedures below.

## Manual Cleanup Procedures

### Clean Stale Artifact Blobs

**CAUTION**: Only clean artifacts older than retention period.

```bash
# Connect to Redis console
az redis console -n gsd-prod-redis -g gsd-prod-rg

# This is a sample - in practice, use a script with proper filtering
# List some artifact keys to inspect timestamps
> SCAN 0 MATCH "gsd:v1:artifacts:*:blob" COUNT 100

# Check TTL of specific key
> TTL "gsd:v1:artifacts:{id}:blob"

# If TTL is -1 (no expiry), the key leaked - can be deleted if old
# DELETE should be used carefully - prefer letting TTL handle it
```

### Reduce Retention Period (Temporary)

If memory pressure is critical, temporarily reduce retention:

```bash
# Current default is 7 days (604800s) for prod
# Reduce to 1 day temporarily
az containerapp update \
  -n gsd-prod-worker \
  -g gsd-prod-rg \
  --set-env-vars "GSD_RETENTION_SECONDS_PROD=86400"

# Remember to revert after memory pressure is resolved
```

### Scale Up Redis (If Budget Allows)

```bash
# Current SKU: Standard C2 (2.5GB)
# Scale to C3 (6GB) if needed
az redis update \
  --name gsd-prod-redis \
  --resource-group gsd-prod-rg \
  --sku Standard \
  --vm-size C3

# Note: This requires a maintenance window and may cause brief interruption
```

## Prevention

### Configure Azure Blob Storage

Ensure all workers have proper Azure Blob configuration:

```bash
# Verify worker env vars (Azure Blob + any legacy S3 config)
az containerapp show -n gsd-prod-worker -g gsd-prod-rg \
  --query "properties.template.containers[0].env[?starts_with(name, 'GSD_AZURE') || starts_with(name, 'GSD_S3') || name == 'GSD_ARTIFACT_DELIVERY_MODE']"
```

### Monitor Blob Upload Success

Check worker logs for artifact upload patterns:

```bash
az containerapp logs show -n gsd-prod-worker -g gsd-prod-rg --tail 100 \
  | grep -E "artifact|screenshot|blob|s3"
```

### Review Retention Settings

| Setting | Default (Dev) | Default (Prod) | Purpose |
|---------|---------------|----------------|---------|
| `GSD_RETENTION_SECONDS_DEV` | 86400 (1d) | - | Task/artifact expiry in dev |
| `GSD_RETENTION_SECONDS_PROD` | - | 604800 (7d) | Task/artifact expiry in prod |

## Escalation

If memory continues to grow after cleanup:

1. **Check for blob storage regression** - Are new artifacts using Redis instead of Blob?
2. **Check worker logs for errors** - Are cleanup jobs running?
3. **Consider Redis scaling** - May need larger SKU
4. **Contact engineering** - May indicate application bug

## Related Documentation

- `docs/ops/RUNBOOK-credential-rotation.md` - If storage keys need rotation
- `CLAUDE.md` - Configuration overview
- ADR-0025 - Artifact storage design
