# Credential Rotation Runbook

This runbook covers rotating credentials for the GSD production environment.

## Overview

GSD production uses these credential types:

| Credential | Consumers | Secret Name in Container Apps |
|------------|-----------|-------------------------------|
| Redis Primary Key | gsd-prod-api, gsd-prod-worker, gsd-prod-mgmt | `docket-url` |
| Storage Account Key | gsd-prod-api, gsd-prod-worker | `s3-secret-access-key` |
| ACR Password | gsd-prod-api, gsd-prod-worker, gsd-prod-mgmt | `acr-password` |
| Log Analytics Shared Key | gsd-prod-aca-env (ACA Environment) | N/A (in env config) |

## Prerequisites

```bash
# Ensure you're logged in and on the correct subscription
az login
az account set -s "Microsoft Azure Sponsorship"

# Verify target resources exist
az group show -n gsd-prod-rg -o table
```

## 1. Rotate Redis Keys

Redis supports two keys (primary and secondary) for zero-downtime rotation.

### Step 1.1: Regenerate Secondary Key (Safe - Not in Use)

```bash
# First, regenerate the secondary key (currently unused)
az redis regenerate-key \
  --name gsd-prod-redis \
  --resource-group gsd-prod-rg \
  --key-type Secondary
```

### Step 1.2: Get New Secondary Key

```bash
# Retrieve the new secondary key
REDIS_HOST=$(az redis show -n gsd-prod-redis -g gsd-prod-rg --query hostName -o tsv)
REDIS_PORT=$(az redis show -n gsd-prod-redis -g gsd-prod-rg --query sslPort -o tsv)
NEW_KEY=$(az redis list-keys -n gsd-prod-redis -g gsd-prod-rg --query secondaryKey -o tsv)

# Construct new docket URL
NEW_DOCKET_URL="rediss://:${NEW_KEY}@${REDIS_HOST}:${REDIS_PORT}/0"
echo "New docket URL constructed (key hidden)"
```

### Step 1.3: Update All Container Apps

```bash
# Update all three apps to use new key
for APP in gsd-prod-api gsd-prod-worker gsd-prod-mgmt; do
  echo "Updating ${APP}..."
  az containerapp secret set \
    --name "$APP" \
    --resource-group gsd-prod-rg \
    --secrets "docket-url=${NEW_DOCKET_URL}"

  # Force revision to pick up new secret
  az containerapp revision restart \
    --name "$APP" \
    --resource-group gsd-prod-rg \
    --revision "$(az containerapp revision list -n "$APP" -g gsd-prod-rg --query '[0].name' -o tsv)"
done
```

### Step 1.4: Verify Apps Are Healthy

```bash
# Check health endpoints
curl -s https://gsd-prod-api.yellowplant-7a34cb33.eastus.azurecontainerapps.io/.well-known/oauth-protected-resource | head -1
curl -s https://gsd-prod-mgmt.yellowplant-7a34cb33.eastus.azurecontainerapps.io/healthz
curl -s https://gsd-prod-worker.yellowplant-7a34cb33.eastus.azurecontainerapps.io/healthz

# Check app status
for APP in gsd-prod-api gsd-prod-worker gsd-prod-mgmt; do
  echo "${APP}:"
  az containerapp show -n "$APP" -g gsd-prod-rg --query "properties.runningStatus" -o tsv
done
```

### Step 1.5: Regenerate Primary Key (Invalidates Old Key)

Once all apps are confirmed healthy on secondary key:

```bash
# Now regenerate the primary key (old key invalidated)
az redis regenerate-key \
  --name gsd-prod-redis \
  --resource-group gsd-prod-rg \
  --key-type Primary
```

## 2. Rotate Storage Account Keys

Storage accounts also support two keys for zero-downtime rotation.

### Step 2.1: Regenerate Key2 (Secondary)

```bash
az storage account keys renew \
  --account-name gsdprodstore \
  --resource-group gsd-prod-rg \
  --key secondary
```

### Step 2.2: Get New Key and Update Apps

```bash
NEW_STORAGE_KEY=$(az storage account keys list \
  --account-name gsdprodstore \
  --resource-group gsd-prod-rg \
  --query '[1].value' -o tsv)

# Update worker (uses storage for artifacts)
az containerapp secret set \
  --name gsd-prod-worker \
  --resource-group gsd-prod-rg \
  --secrets "s3-secret-access-key=${NEW_STORAGE_KEY}"

# Note: API also needs this for artifact retrieval
az containerapp secret set \
  --name gsd-prod-api \
  --resource-group gsd-prod-rg \
  --secrets "s3-secret-access-key=${NEW_STORAGE_KEY}"

# Restart to pick up new secrets
for APP in gsd-prod-worker gsd-prod-api; do
  az containerapp revision restart \
    --name "$APP" \
    --resource-group gsd-prod-rg \
    --revision "$(az containerapp revision list -n "$APP" -g gsd-prod-rg --query '[0].name' -o tsv)"
done
```

### Step 2.3: Verify Artifact Operations

```bash
# Submit a test job and verify screenshot artifacts work
# Check worker logs for artifact upload success
az containerapp logs show -n gsd-prod-worker -g gsd-prod-rg --tail 50 | grep -i artifact
```

### Step 2.4: Regenerate Key1 (Primary)

```bash
az storage account keys renew \
  --account-name gsdprodstore \
  --resource-group gsd-prod-rg \
  --key primary
```

## 3. Rotate ACR Password

ACR supports password and password2 for zero-downtime rotation.

### Step 3.1: Regenerate password2

```bash
az acr credential renew \
  --name gsdprodacr \
  --password-name password2
```

### Step 3.2: Update All Apps

```bash
NEW_ACR_PASSWORD=$(az acr credential show \
  --name gsdprodacr \
  --query 'passwords[1].value' -o tsv)

for APP in gsd-prod-api gsd-prod-worker gsd-prod-mgmt; do
  az containerapp secret set \
    --name "$APP" \
    --resource-group gsd-prod-rg \
    --secrets "acr-password=${NEW_ACR_PASSWORD}"

  az containerapp revision restart \
    --name "$APP" \
    --resource-group gsd-prod-rg \
    --revision "$(az containerapp revision list -n "$APP" -g gsd-prod-rg --query '[0].name' -o tsv)"
done
```

### Step 3.3: Verify Image Pull Works

```bash
# Trigger a new deployment to verify image pull
az containerapp update \
  --name gsd-prod-api \
  --resource-group gsd-prod-rg \
  --set-env-vars "GSD_ROTATION_CHECK=$(date +%s)"

# Check revision is running
az containerapp revision list -n gsd-prod-api -g gsd-prod-rg --query '[0].properties.runningState' -o tsv
```

### Step 3.4: Regenerate password (Primary)

```bash
az acr credential renew \
  --name gsdprodacr \
  --password-name password
```

## 4. Rotate Log Analytics Shared Key

Log Analytics key regeneration requires REST API or portal.

### Option A: Via Azure Portal

1. Navigate to: Azure Portal > Log Analytics workspaces > gsd-prod-logs
2. Settings > Agents management
3. Click "Regenerate" next to Secondary key
4. Update ACA environment (requires redeployment)
5. After verification, regenerate Primary key

### Option B: Via REST API

```bash
# Get subscription ID
SUB_ID=$(az account show --query id -o tsv)

# Regenerate secondary shared key
az rest --method POST \
  --uri "https://management.azure.com/subscriptions/${SUB_ID}/resourceGroups/gsd-prod-rg/providers/Microsoft.OperationalInsights/workspaces/gsd-prod-logs/regenerateSharedKey?api-version=2020-08-01" \
  --body '{"keyName": "secondary"}'
```

### Step 4.1: Update ACA Environment

The ACA environment configuration cannot be updated in-place for Log Analytics keys.
You need to redeploy the environment using the IaC:

```bash
# Redeploy (the IaC will call listKeys() and get the new key)
cd /path/to/gsd-browser
./infra/scripts/deploy.sh
```

### Step 4.2: Verify Logs Flowing

```bash
# Check Log Analytics for recent logs
az monitor log-analytics query \
  --workspace gsd-prod-logs \
  --resource-group gsd-prod-rg \
  --analytics-query "ContainerAppConsoleLogs | take 10" \
  --timespan "PT1H"
```

## Rollback Procedures

### If Redis Rotation Fails

```bash
# Regenerate the key again (gets a new random key)
az redis regenerate-key \
  --name gsd-prod-redis \
  --resource-group gsd-prod-rg \
  --key-type Primary

# Update apps with new key (repeat steps 1.2-1.4)
```

### If Storage Key Rotation Fails

```bash
# Storage keys can be regenerated again
az storage account keys renew \
  --account-name gsdprodstore \
  --resource-group gsd-prod-rg \
  --key primary

# Repeat update steps
```

### If ACR Password Rotation Fails

```bash
# Regenerate ACR password
az acr credential renew \
  --name gsdprodacr \
  --password-name password

# Repeat update steps
```

### General Rollback: Redeploy Infrastructure

If rotation causes cascading failures, a full redeployment will regenerate all secrets:

```bash
cd /path/to/gsd-browser
./infra/scripts/deploy.sh
```

## Post-Rotation Checklist

- [ ] All Container Apps running (check `az containerapp list -g gsd-prod-rg -o table`)
- [ ] API health endpoint returns 200
- [ ] Worker health endpoint returns 200
- [ ] Management API health endpoint returns 200
- [ ] Logs flowing to Log Analytics
- [ ] Submit a test job and verify completion
- [ ] Dashboard can list sessions
- [ ] Screenshots are captured and retrievable

## Schedule

Recommended rotation frequency:
- Redis keys: Quarterly
- Storage keys: Quarterly
- ACR password: After any suspected exposure
- Log Analytics: After any suspected exposure

## Related Documentation

- [Azure Cache for Redis Keys](https://learn.microsoft.com/en-us/azure/azure-cache-for-redis/cache-configure#access-keys)
- [Storage Account Keys](https://learn.microsoft.com/en-us/azure/storage/common/storage-account-keys-manage)
- [ACR Admin Credentials](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-authentication#admin-account)
