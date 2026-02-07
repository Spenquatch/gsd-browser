# Queue Backlog Runbook

This runbook covers investigating and mitigating queue backlog in production.

## Symptoms

- Jobs remain in `queued` for multiple minutes.
- Worker health is up but throughput is low.
- Dashboard shows sessions stuck in “create/active” without progress.

## Quick checks

### 1) Health endpoints (no auth)

```bash
curl -fsS "https://<apiFqdn>/.well-known/oauth-protected-resource" >/dev/null
curl -fsS "https://<workerFqdn>/healthz/worker" >/dev/null
```

### 2) Queue metrics (requires `gsd:admin` JWT)

Management API metrics:

```bash
curl -fsS \
  -H "Authorization: Bearer $GSD_TOKEN" \
  -H "Origin: https://browse.buildconnectors.com" \
  "https://<mgmtFqdn>/metrics" | rg "gsd_docket_"
```

Interpretation:
- `gsd_docket_stream_len`: ready-to-claim messages (backlog signal).
- `gsd_docket_stream_oldest_age_seconds`: how long the oldest queued message has waited.
- `gsd_docket_queue_len`: scheduled tasks (can be >0 even when healthy).
- `gsd_docket_queue_oldest_overdue_seconds`: if >0, the earliest scheduled task is overdue.

### 3) Worker diagnostics logs (if enabled)

If `GSD_WORKER_DIAGNOSTICS_INTERVAL_S` is set on workers, logs include `worker.docket.depth` with
queue/stream sizes and oldest-age hints.

```bash
az containerapp logs show -g gsd-prod-rg -n gsd-prod-worker --tail 200
```

## Common causes

### Worker not consuming

- Worker crashed / restart loop.
- Worker concurrency set to `0`.
- Redis connectivity issues.

Actions:
- Check worker revision status and logs.
- Verify `FASTMCP_DOCKET_CONCURRENCY` > 0 on worker.
- Verify Redis resource health in Azure.

### Queue is healthy but jobs are slow

- Target site is slow or blocking automation.
- LLM provider latency or rate limiting.

Actions:
- Inspect job result/error (via MCP tooling or mgmt job endpoints).
- Consider reducing max concurrency temporarily to stabilize.

## Alert Drill Checklist

Use this checklist to verify the alert pipeline works end-to-end:

1. **Acknowledge**: Confirm alert email arrives at `gsd-prod-alerts-ag` receivers.
2. **Triage**: Open Azure Portal > Monitor > Alerts; find the fired `gsd-prod-queue-backlog` alert.
3. **First graph**: Check Azure Monitor metrics for Redis or run:
   ```bash
   curl -fsS -H "Authorization: Bearer $GSD_TOKEN" \
     -H "Origin: https://browse.buildconnectors.com" \
     "https://gsd-prod-mgmt.yellowplant-7a34cb33.eastus.azurecontainerapps.io/metrics" | python3 -m json.tool
   ```
4. **Correlate**: Run the alert KQL query manually:
   ```kql
   ContainerAppConsoleLogs_CL
   | where ContainerAppName_s == "gsd-prod-worker"
   | where Log_s has "worker.docket.depth"
   | extend payload = parse_json(Log_s)
   | extend stream_oldest = todouble(payload.docket_stream_oldest_age_s)
   | extend queue_overdue = todouble(payload.docket_queue_oldest_overdue_s)
   | where stream_oldest > 300 or queue_overdue > 300
   | project TimeGenerated, stream_oldest, queue_overdue
   | order by TimeGenerated desc
   | take 20
   ```
5. **Resolve or escalate**: If backlog is draining, resolve the alert. If growing, follow mitigations below.

## Mitigations

### Scale worker replicas

If backlog is real and capacity is the issue, increase worker scaling limits (or temporarily set
min replicas > 1). Do this via IaC and deploy.

### Drain problematic jobs

If a specific job is stuck/looping, cancel it (admin-only tooling) and re-submit with reduced
max steps/timeouts.

## Escalation

If `gsd_docket_stream_oldest_age_seconds` keeps increasing and worker replicas are healthy, page
engineering: this can indicate redelivery/claim issues or a Redis regression.

