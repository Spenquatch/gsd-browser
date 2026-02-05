# Rollback (Azure Container Apps)

This runbook documents rolling back the backend without rebuilding images.

## Identify last known-good

ACR tags (most recent first):
```bash
az acr repository show-tags -n gsdprodacr --repository gsd-browser --orderby time_desc --top 10 -o table
```

Current running revisions and images:
```bash
az containerapp show -g gsd-prod-rg -n gsd-prod-api --query "{rev:properties.latestReadyRevisionName,image:properties.template.containers[0].image}" -o json
az containerapp show -g gsd-prod-rg -n gsd-prod-worker --query "{rev:properties.latestReadyRevisionName,image:properties.template.containers[0].image}" -o json
az containerapp show -g gsd-prod-rg -n gsd-prod-mgmt --query "{rev:properties.latestReadyRevisionName,image:properties.template.containers[0].image}" -o json
```

## Roll back by activating a previous revision (fastest)

List revisions:
```bash
az containerapp revision list -g gsd-prod-rg -n gsd-prod-api --query "[].{name:name,active:properties.active,createdTime:properties.createdTime,traffic:properties.trafficWeight}" -o table
```

Activate a previous revision:
```bash
az containerapp revision activate -g gsd-prod-rg -n gsd-prod-api --revision <revision-name>
az containerapp revision activate -g gsd-prod-rg -n gsd-prod-worker --revision <revision-name>
az containerapp revision activate -g gsd-prod-rg -n gsd-prod-mgmt --revision <revision-name>
```

## Verify health post-rollback

```bash
curl -fsS "https://<apiFqdn>/.well-known/oauth-protected-resource" >/dev/null
curl -fsS "https://<workerFqdn>/healthz" >/dev/null
curl -fsS "https://<workerFqdn>/healthz/worker" >/dev/null
curl -fsS "https://<mgmtFqdn>/healthz" >/dev/null
```

If the rollback is incomplete, check recent Container App logs and revision health.

