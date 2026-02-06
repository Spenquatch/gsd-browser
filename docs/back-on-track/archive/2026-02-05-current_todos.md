# TODOs (Phase 4 only) — 2026-02-05

This list is scoped to the remaining Phase 4 work from the back-on-track plan:
release process + documentation drift + observability. Phases 1–3 are treated as done/validated.

## 4.1 Release process (GitHub Actions)

- [ ] Confirm repo secrets exist and are named consistently (see `docs/ops/CI-CD.md`).
- [ ] Use `.github/workflows/backend-build.yml` to build/push immutable backend tags to ACR.
- [ ] Use `.github/workflows/deploy-prod.yml` for production deploys (environment approvals).
- [ ] Use `.github/workflows/dashboard-build.yml` to build/deploy `gsd-dashboard` with build-time Vite env vars.
- [ ] Remove or keep legacy `.github/workflows/azure-deploy.yml` intentionally (it is now `workflow_dispatch` only).

## 4.2 Docs drift

- [ ] Keep env var docs consolidated in `gsd-browser/docs/ENV_VARS.md`.
- [ ] Update ADRs when implementation changes (especially deployment + storage assumptions).

## 4.3 Observability

- [ ] Add authenticated metrics endpoint (`/metrics`) on the management API.
- [ ] Add alert stubs and runbooks for queue backlog + worker failures.

## Follow-ups (product UX)

- [x] Dashboard screenshot thumbnails: mgmt `/api/v1/sessions/{id}/screenshots` returns signed `url` values for Azure/S3-backed artifacts and the dashboard renders them (fallback when `data_base64` is missing). Deploy to prod to pick up the fix.
