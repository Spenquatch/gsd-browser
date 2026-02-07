# CI/CD (GitHub Actions) — Prod Release Process

This repo uses GitHub Actions to build and deploy the backend (`gsd-browser`) and the dashboard (`gsd-dashboard`).

## Workflows

- Backend build/push (ACR): `.github/workflows/backend-build.yml`
- Backend deploy (Bicep): `.github/workflows/deploy-prod.yml`
- Dashboard build/deploy (Static Web Apps): `.github/workflows/dashboard-build.yml`
- Infra guards (PR): `.github/workflows/infra-guard.yml`
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

## Required checks (pre-merge)

The following checks must pass before merging to `main`:

- `make py-lint` — Ruff lint on `gsd-browser/`
- `make py-test` — pytest suite for `gsd-browser/`
- `python3 infra/scripts/guard_no_secret_outputs.py` — no secret-ish outputs in Bicep modules (automated via `infra-guard.yml` on PRs touching `infra/modules/`)

Recommended (not yet enforced in CI):

- `make fe-lint` — ESLint on `gsd-dashboard/` (run manually if dashboard changes were made)
- `make py-smoke` — end-to-end smoke test (requires running services)

### Legacy workflow

`.github/workflows/azure-deploy.yml` is kept as a **deprecated, manual-only** fallback. It is gated
behind `workflow_dispatch` and its description directs users to `deploy-prod.yml`. It remains in the
repo in case a combined build+deploy+dashboard workflow is needed for emergency recovery, but normal
releases should use the split workflows (`backend-build.yml` → `deploy-prod.yml` → `dashboard-build.yml`).

## Infra guards (Bicep)

This repo includes a deterministic CI guard that fails PRs if any `infra/modules/*.bicep` declares
secret-ish outputs (e.g., output names containing `secret`, `password`, `token`, or a `*Key*`-style
segment).

Run locally:

- `python3 infra/scripts/guard_no_secret_outputs.py`

Notes:

- The guard is intentionally name-based to keep it deterministic and fast.
- A small allowlist exists in `infra/scripts/guard_no_secret_outputs.py` for known-benign cases
  like `accessKeyId`.
