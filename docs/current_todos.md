# Suggested TODOs (needs validation) — 2026-02-05

This is a **suggested** follow-up list based on the current deployed state documented in
`docs/current.md`. Items here are intentionally framed as **research-first** tasks: validate the
assumptions, discover missing work, and then decide what to implement.

## Suggested priorities (research-first)

### Suggested P0 — security + operational safety

- [ ] Suggested: **Rotate Redis credentials** (validate whether secrets leaked in logs and whether rotation is required anyway).
  - Research:
    - Confirm which revisions logged `FASTMCP_DOCKET_URL` with password (Container App logs + timestamps).
    - Confirm whether the Redis credential is a primary/secondary key and rotation path.
    - Confirm which Container Apps use the `docket-url` secret (`gsd-prod-api`, `gsd-prod-worker`, `gsd-prod-mgmt`).
  - Deliverable: a rotation runbook + verification steps (no downtime or controlled rollout).

- [ ] Suggested: **Audit “Origin required” behavior on Management API** (ensure it’s intentional and doesn’t break tooling).
  - Research:
    - Identify which middleware is returning `{"error":"origin_not_allowed"}` and when.
    - Confirm whether dashboards/scripts/automations always send an `Origin` header.
  - Deliverable: a clear policy decision + consistent behavior across prod/dev.

- [ ] Suggested: **Review secret handling in logs** across API/worker/mgmt.
  - Research:
    - Search for any remaining prints of URLs/headers (especially `Authorization`, Redis URLs, S3 creds).
  - Deliverable: centralized redaction utilities + a “safe logging” checklist.

### Suggested P1 — durability + cost

- [ ] Suggested: **Replace Redis-backed screenshot blobs with real object storage**.
  - Current reality: screenshots fall back to Redis when `GSD_S3_ENDPOINT_URL` points at Azure Blob (not S3-compatible).
  - Research:
    - Decide target storage: Azure Blob native SDK, S3-compatible service, or R2/etc.
    - Define lifecycle/retention, encryption, and access model (private + presigned URLs vs inline base64).
    - Confirm expected artifact volume and cost profile (Redis memory pressure vs object storage).
  - Deliverable: an artifact storage ADR + implementation plan + migration strategy.

- [ ] Suggested: **Hardening for artifact retrieval APIs**.
  - Research:
    - Confirm payload size limits and front-end behavior when `include_data=true`.
    - Decide whether to add pagination, “signed URL only” mode, or downscaled thumbnails.
  - Deliverable: versioned API contract for artifacts + UI behavior spec.

### Suggested P1 — “live sessions” experience (streaming)

- [ ] Suggested: **Decide and document the production streaming architecture**.
  - Current reality: dashboard lists sessions + artifacts, but live streaming is not hardened for prod.
  - Research:
    - Should streaming be a dedicated Container App (`serve-streaming`) vs embedded inside worker?
    - How will `stream_url` be computed and exposed? (`GSD_STREAMING_PUBLIC_HOST`, ingress, TLS)
    - How will multi-replica workers route viewers to the correct streamer?
  - Deliverable: an ADR that pins the architecture + a deployment plan + success criteria.

### Suggested P2 — release process + reproducibility

- [ ] Suggested: **Introduce CI/CD to pin releases and avoid “manual env var” drift** (especially for the dashboard).
  - Research:
    - Decide source of truth for prod env values (Bicep parameters vs CI secrets vs SWA build pipeline).
    - Confirm how the Static Web App should be deployed (GitHub Actions, Azure DevOps, or `swa deploy` in CI).
  - Deliverable: repeatable pipeline that builds backend images + dashboard with immutable versions.

- [ ] Suggested: **Reconcile infra plans vs reality**.
  - Research:
    - Compare `infra/` Bicep + `docs/adr/*` against the currently deployed resources and runtime behavior.
  - Deliverable: “diff report” + changes needed to bring infra-as-code back in sync.

### Suggested P2 — observability + debugging ergonomics

- [ ] Suggested: **Operational dashboards/alerts** for queue depth and worker liveness.
  - Research:
    - Identify which metrics/logs exist today (ACA logs, Redis metrics).
    - Decide SLOs and alert thresholds (queued age, processing latency, failure rate).
  - Deliverable: minimal alerts + runbook links.

- [ ] Suggested: **First-class run history** (beyond current retention keys).
  - Research:
    - Decide whether “sessions” should be an explicit durable record (DB) vs derived from redis keys.
    - Decide retention needs and tenant isolation requirements.
  - Deliverable: storage + API contract proposal for historical runs.

## Suggested validation checklist (quick)

- [ ] Suggested: Confirm current prod versions:
  - `az containerapp show -n gsd-prod-api -g gsd-prod-rg --query properties.template.containers[0].image -o tsv`
  - `az containerapp show -n gsd-prod-worker -g gsd-prod-rg --query properties.template.containers[0].image -o tsv`
  - `az containerapp show -n gsd-prod-mgmt -g gsd-prod-rg --query properties.template.containers[0].image -o tsv`
- [ ] Suggested: Submit a job and confirm:
  - `job_submit.session_id == job_wait.session_id`
  - `/api/v1/sessions` includes the session
  - `/api/v1/sessions/{id}/screenshots` returns records with `data_base64` (for Redis-backed blobs)

## Suggested pointers (where to look)

- Sessions ownership + listing:
  - `gsd-browser/src/gsd_browser/optionb/task_ownership.py`
  - `gsd-browser/src/gsd_browser/optionb/compat_jobs.py`
  - `gsd-browser/src/gsd_browser/management_api/app.py`
- Session ID linking (job → tool execution):
  - `gsd-browser/src/gsd_browser/optionb/job_store.py`
  - `gsd-browser/src/gsd_browser/fastmcp_v2_stdio.py`
  - `gsd-browser/src/gsd_browser/mcp_server.py`
- Artifacts (screenshots):
  - `gsd-browser/src/gsd_browser/optionb/screenshot_artifacts.py`
  - `gsd-browser/src/gsd_browser/optionb/artifact_index.py`
- Dashboard build-time config + Clerk:
  - `gsd-dashboard/src/main.tsx`
  - `gsd-dashboard/src/lib/auth.ts`
  - `docs/adr/ADR-0027-dashboard-frontend-rebuild.md`

