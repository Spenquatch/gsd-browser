# Common `az` queries (ACA + ACR)

## Container App overview

```bash
az containerapp show -n gsd-prod-api -g gsd-prod-rg -o jsonc
az containerapp ingress show -n gsd-prod-api -g gsd-prod-rg -o jsonc
```

## Revisions / replicas

```bash
az containerapp revision list -n gsd-prod-api -g gsd-prod-rg -o table
az containerapp revision show -n gsd-prod-api -g gsd-prod-rg --revision gsd-prod-api--0000008 -o jsonc
az containerapp replica list -n gsd-prod-api -g gsd-prod-rg --revision gsd-prod-api--0000008 -o table
```

## Logs

```bash
az containerapp logs show -n gsd-prod-api -g gsd-prod-rg --tail 200
az containerapp logs show -n gsd-prod-api -g gsd-prod-rg --type system --tail 200
```

## ACR

```bash
az acr show -n gsdprodacr -o jsonc
az acr repository list -n gsdprodacr -o table
az acr repository show-tags -n gsdprodacr --repository gsd-browser -o table
az acr login -n gsdprodacr
```

