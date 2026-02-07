---
name: az-gsd-browser-deploy
description: "Azure az CLI workflows for the gsd-browser repo: build/push Docker images to Azure Container Registry (ACR), deploy/rollback Azure Container Apps (ACA) revisions (especially gsd-prod-api in gsd-prod-rg), tail logs, and verify health/MCP endpoints. Use when asked to redeploy gsd-browser to ACA, debug a failing/unhealthy revision, rotate image tags, or validate MCP over HTTP (SSE) after a deploy."
---

# Az Gsd Browser Deploy

## Preferred prod deploy (GitHub Actions)

Production deploys are managed via GitHub Actions (see `docs/ops/CI-CD.md` in the repo):

- Backend build/push (ACR): `.github/workflows/backend-build.yml`
- Backend deploy (Bicep): `.github/workflows/deploy-prod.yml`
- Dashboard build/deploy (Static Web Apps): `.github/workflows/dashboard-build.yml`
- Legacy all-in-one (deprecated / manual only): `.github/workflows/azure-deploy.yml`

This skill focuses on `az` CLI for inspection, rollback, and incident/unblock deploys.

## Quick start (incident deploy via `az` CLI)

Run the incident deploy script (inspect → build/push → update → verify):

```bash
./codex/skills/az-gsd-browser-deploy/scripts/deploy_prod_api.sh
```

## Assumptions

- Run from the repo root (or set `GSD_REPO_ROOT`).
- Dockerfile: `gsd-browser/docker/Dockerfile`
- Azure resources (prod defaults):
  - Resource group: `gsd-prod-rg`
  - Container App: `gsd-prod-api`
  - ACR: `gsdprodacr` (repo `gsd-browser`)
  - Public FQDN: `gsd-prod-api.yellowplant-7a34cb33.eastus.azurecontainerapps.io`
- MCP endpoint: `https://<fqdn>/mcp` (streamable HTTP / SSE).
- If verifying MCP calls: set `GSD_TOKEN` in the current shell.

## Deploy workflow (safe default)

1. Inspect current state (image, revisions, env, ingress):
   - `scripts/inspect_prod_api.sh`
2. Build + push a unique ACR tag (never push a “mystery latest”):
   - `scripts/build_push_prod_api_image.sh`
3. Update the Container App image (creates a new revision in Single mode):
   - `scripts/update_prod_api_image.sh`
4. Verify:
   - `scripts/verify_prod_api.sh` (health loop + optional MCP calls)
5. If unhealthy, roll back:
   - `scripts/rollback_prod_api.sh`

## Notes on CI/CD tags

- GitHub Actions default backend image tag is `sha-<gitsha12>` (see `.github/workflows/backend-build.yml`).
- If doing an incident deploy from your laptop, use a unique tag (this skill defaults to `fix-<sha>-<utc_timestamp>`)
  to avoid overwriting the CI-built `sha-*` tags.

## Debug workflow (when a revision is Unhealthy/Failed)

1. Tail app logs and system events:
   - `az containerapp logs show -n gsd-prod-api -g gsd-prod-rg --tail 200`
   - `az containerapp logs show -n gsd-prod-api -g gsd-prod-rg --type system --tail 200`
2. Check revision + replica state:
   - `az containerapp revision list -n gsd-prod-api -g gsd-prod-rg -o table`
   - `az containerapp replica list -n gsd-prod-api -g gsd-prod-rg --revision <rev>`
3. Validate ingress/port + probe endpoints:
   - `az containerapp ingress show -n gsd-prod-api -g gsd-prod-rg -o jsonc`
   - `curl -fsS --max-time 10 "https://<fqdn>/.well-known/oauth-protected-resource"`
4. Smoke MCP (requires `GSD_TOKEN`):
   - `scripts/smoke_mcp.sh`

## Claude Code config note (mcp-remote)

Prefer this header formatting (spaces matter):

```json
{
  "mcpServers": {
    "gsd": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "https://gsd-prod-api.yellowplant-7a34cb33.eastus.azurecontainerapps.io/mcp",
        "--header",
        "Authorization: Bearer ${GSD_TOKEN}"
      ]
    }
  }
}
```

## References

- Parameter/env reference: `references/env-and-defaults.md`
- Common `az` queries: `references/az-queries.md`
- CI/CD reference: `references/ci-cd.md`

**Examples from other skills:**
- Brand styling: PowerPoint template files (.pptx), logo files
- Frontend builder: HTML/React boilerplate project directories
- Typography: Font files (.ttf, .woff2)

**Appropriate for:** Templates, boilerplate code, document templates, images, icons, fonts, or any files meant to be copied or used in the final output.

---

**Not every skill requires all three types of resources.**
