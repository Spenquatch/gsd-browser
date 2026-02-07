# CI/CD (GitHub Actions) — prod release summary

Canonical source in repo: `docs/ops/CI-CD.md`.

## What deploys via GitHub Actions

- **Backend image build/push to ACR**: `.github/workflows/backend-build.yml`
  - On `push` to `main` (and tags) for backend-related paths, and via `workflow_dispatch`.
  - Default tag format: `sha-<gitsha12>` (or a git tag name).
  - Uploads an artifact named `backend-image` containing:
    - `image_tag.txt`
    - `image.txt`

- **Backend deploy to Azure (Bicep)**: `.github/workflows/deploy-prod.yml`
  - `workflow_dispatch` only: you provide `image_tag` (e.g. `sha-...`).
  - Runs `./infra/scripts/deploy.sh` which updates the prod Container Apps via infra-as-code.
  - Post-deploy smoke checks are unauthenticated:
    - API: `/.well-known/oauth-protected-resource`
    - Worker: `/healthz` and `/healthz/worker`
    - Mgmt: `/healthz`

- **Dashboard deploy (Static Web Apps)**: `.github/workflows/dashboard-build.yml`

## What is legacy

- `.github/workflows/azure-deploy.yml` is deprecated and intended for manual use only.

## When to use `az` CLI instead of GitHub Actions

Use `az` CLI for:

- **Inspection** during an incident (revisions/replicas/logs).
- **Rollback** using `az containerapp revision activate` (fastest) — see `docs/ops/ROLLBACK.md`.
- **Emergency unblock deploy** only when Actions cannot be used quickly; prefer unique tags that do not overwrite `sha-*`.

