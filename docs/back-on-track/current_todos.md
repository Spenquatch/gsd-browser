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

- [ ] Dashboard screenshot thumbnails: mgmt `/api/v1/sessions/{id}/screenshots` currently only returns `data_base64` for legacy Redis-backed artifacts. For Azure Blob-backed artifacts, add signed URLs and update the dashboard to render them.
