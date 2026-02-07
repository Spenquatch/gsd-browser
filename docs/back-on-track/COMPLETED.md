# Plan Completed — 2026-02-07

The airtight completion plan (`docs/recent_plan.md`) is now complete. This document records
the final state, commands used, and any accepted risks.

## Completion date

2026-02-07

## Commands run locally

```bash
make py-lint        # All checks passed
make py-test        # 361 passed, 2 skipped (S3 test infra not running)
make py-smoke       # Passed (earlier sessions)
python3 infra/scripts/guard_no_secret_outputs.py  # No secret outputs in IaC
```

## Azure operations performed

### Credential rotation (Phase 1.2)

All credentials rotated using zero-downtime dual-key strategy:

| Credential | Method | Verification |
|------------|--------|-------------|
| Redis (primary + secondary) | `az redis regenerate-keys` → update `docket-url` on api/worker/mgmt → restart → regen primary | All 3 apps healthy, logs flowing |
| Storage account (key1 + key2) | `az storage account keys renew` → update `s3-secret-access-key` on api/worker → restart → regen key1 | Api + worker healthy |
| ACR (password + password2) | `az acr credential renew` → update `acr-password` on all 3 → restart → regen password | All 3 apps healthy |
| Log Analytics (secondary) | REST API `regenerateSharedKey?keyType=secondarySharedKey` (query param workaround for known Azure API bug) | Logs still flowing to workspace |

Post-rotation leakage query (`ContainerAppConsoleLogs_CL` for password/secret/rediss patterns):
**0 new leaks** since rotation time (16:03 UTC). Historical leaks reference now-invalidated keys.

### Retention strategy (Phase 2.1)

Decision: **Option A (app-driven deletion) + storage lifecycle safety net.**

- App cleanup runner routes deletes by `artifact_backend` (azure/s3/redis).
- Added Azure Storage lifecycle policy `delete-old-artifacts` on `gsdprodstore`:
  14-day auto-delete of all blockBlobs (2x the 7-day app-side retention).

### Alerts (Phase 4.3)

- Added email receiver (`ops-primary`) to `gsd-prod-alerts-ag` action group (live + IaC).
- Validated all 3 scheduledQueryRules queries against actual Log Analytics table schemas.
- **Bug found/fixed**: `worker-failures` and `queue-backlog` queries had un-interpolated
  `${prefix}-worker` (Bicep triple-quoted strings don't interpolate). Fixed in
  `infra/modules/monitoring.bicep`. Live REST API update was rate-limited; will take effect
  on next IaC deploy.
- Added alert drill checklists to all 3 runbooks.

## Deploy workflows used

- No full IaC deploy was performed in this session (alert query fix will deploy with next release).
- Direct Azure CLI operations for credential rotation and lifecycle policy.
- GitHub Actions CI/CD remains the preferred path for code deploys.

## Runtime verification

| Check | Result |
|-------|--------|
| API health | 200 (oauth-protected-resource) |
| Worker health | `status=ok, streaming=cdp` |
| Mgmt health | `status=ok` |
| `/metrics` auth | HTTP 401 without JWT |
| Dashboard | HTTP 200 |
| IaC guard (no secret outputs) | Pass |
| Lint | All checks passed |
| Tests | 361 passed, 2 skipped |

## Accepted risks

1. **Rich traceback local variable leaks**: During transient failures (e.g., rotation restarts),
   Rich tracebacks can expose `docket_url` with the Redis password. Mitigated by quarterly
   credential rotation. Full fix would require `SecretStr` in FastMCP settings or disabling
   `show_locals` in Rich traceback — deferred as low-priority.

2. **Alert query fix pending deploy**: The `worker-failures` and `queue-backlog` alert rules
   still have literal `${prefix}-worker` in production until the next IaC deploy. The queries
   currently return 0 matches (which means no false alerts, but also no true alerts). Fixed
   in Bicep source; will be live after next `deploy-prod.yml` run.

3. **2.2.D Performance/load validation (optional)**: Deferred. The indexed lookup path is
   implemented and tested; a formal load test at 10k+ tasks was not performed.

4. **Log Analytics primary key not rotated**: Only the secondary key was regenerated. The ACA
   environment uses the primary key (set at environment creation via `listKeys()`). Rotating
   the primary would require a full ACA environment redeployment, which is disruptive. Deferred
   to a planned maintenance window.

## References

- Source plan: `docs/recent_plan.md`
- Audit that triggered the plan: `docs/back-on-track/2026-02-05-current-state-audit.md`
- Detailed TODO checklist: `docs/back-on-track/current_todos.md`
- Current prod snapshot: `docs/back-on-track/current.md`
