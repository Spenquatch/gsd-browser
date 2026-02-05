# CI/CD (GitHub Actions) — Prod Release Process

This repo uses GitHub Actions to build and deploy the backend (`gsd-browser`) and the dashboard (`gsd-dashboard`).

## Workflows

- Backend build/push (ACR): `.github/workflows/backend-build.yml`
- Backend deploy (Bicep): `.github/workflows/deploy-prod.yml`
- Dashboard build/deploy (Static Web Apps): `.github/workflows/dashboard-build.yml`
- Legacy all-in-one (deprecated / manual only): `.github/workflows/azure-deploy.yml`

## Required GitHub settings

### Environments

Create a GitHub Environment named `prod` and enable required reviewers. Both deploy workflows use `environment: prod`.

### Secrets

Azure (OIDC):
- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`

Backend deploy:
- `ANTHROPIC_API_KEY` (required by `infra/scripts/deploy.sh`)

Static Web Apps:
- `AZURE_STATIC_WEB_APPS_API_TOKEN` (deployment token for the prod SWA)

Dashboard build-time Vite env:
- `VITE_CLERK_PUBLISHABLE_KEY`
- `VITE_GSD_API_BASE_URL` (should point at the management API base URL, e.g. `https://gsd-prod-mgmt.<domain>`)
- `VITE_GSD_CLERK_JWT_TEMPLATE` (usually `gsd`)

## Typical release flow

1) Build and push an immutable backend image tag (ACR)
- Run `Backend Build (ACR)` (manual) or merge to `main`.
- Output artifact `backend-image` includes `image_tag.txt` and `image.txt`.

2) Deploy to prod (Bicep)
- Run `Deploy Prod (Bicep)` and pass `image_tag` from step (1).
- Post-deploy, the workflow performs unauthenticated health checks:
  - `/.well-known/oauth-protected-resource` (API)
  - `/healthz` and `/healthz/worker` (worker)
  - `/healthz` (mgmt)

3) Deploy dashboard (SWA)
- Run `Dashboard Build & Deploy (SWA)` to build and upload the `gsd-dashboard` bundle with the correct build-time env.

## Rollback

See `docs/ops/ROLLBACK.md`.

