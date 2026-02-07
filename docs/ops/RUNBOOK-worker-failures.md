# Worker Failures Runbook

This runbook covers diagnosing worker crashes, stuck workers, and redelivery regressions.

## Symptoms

- `/healthz/worker` fails or returns unhealthy status.
- Backlog grows (`/metrics` shows high `gsd_docket_stream_oldest_age_seconds`).
- Logs show worker startup failures.

## Checks

### 1) Health endpoints

```bash
curl -fsS "https://<workerFqdn>/healthz/worker"
```

### 2) Container App revision and recent logs

```bash
az containerapp show -g gsd-prod-rg -n gsd-prod-worker --query "{rev:properties.latestReadyRevisionName,image:properties.template.containers[0].image}" -o json
az containerapp logs show -g gsd-prod-rg -n gsd-prod-worker --tail 200
```

Look for:
- `Docket worker did not enter polling loop` (startup crash)
- `Docket worker stopped unexpectedly` (worker died after starting)
- `redis.xautoclaim_unsupported` (informational; compat path in use)
- `worker.docket.depth_failed` (Redis polling/diagnostics failed)

### 3) Redis health

Use Azure portal metrics (latency, server load, memory) and ensure Redis is reachable from ACA.

## Common causes

### Redis 6.0 redelivery edge cases

Azure Cache for Redis 6.0 can require the XAUTOCLAIM compat path. If redelivery regresses, backlog
will increase and jobs may stall.

Actions:
- Confirm compat log event appears at least once per worker (`redis.xautoclaim_unsupported`).
- Focus paging on backlog age rather than the compat log itself.

### Browser/Chrome failures

If Chrome fails to start or crashes repeatedly, worker can become unhealthy.

Actions:
- Look for browser startup errors in logs.
- Verify container image includes Chrome and permissions are correct.

### 4) XAUTOCLAIM compat path visibility

The worker patches `redis-py` to fall back to `XPENDING` + `XCLAIM` when the Redis server does not
support `XAUTOCLAIM` (Redis < 6.2). When the fallback activates, the worker logs
`redis.xautoclaim_unsupported` once per process lifetime.

Use this Log Analytics (KQL) query to check whether the compat path is active:

```kql
ContainerAppConsoleLogs_CL
| where ContainerAppName_s == "gsd-prod-worker"
| where Log_s has "redis.xautoclaim_unsupported"
| project TimeGenerated, Log_s
| order by TimeGenerated desc
| take 20
```

- **Rows returned**: the compat path is in use; Redis server is < 6.2.
- **No rows**: either the worker hasn't restarted recently, or Redis supports `XAUTOCLAIM` natively.

This is informational and should not page. If the compat path is active, redelivery still works but
may be slightly less efficient. Upgrading Redis to 6.2+ removes the need for the patch.

## Alert Drill Checklist

Use this checklist to verify the alert pipeline works end-to-end:

1. **Acknowledge**: Confirm alert email arrives at `gsd-prod-alerts-ag` receivers.
2. **Triage**: Open Azure Portal > Monitor > Alerts; find the fired `gsd-prod-worker-failures` alert.
3. **First graph**: Check worker revision status:
   ```bash
   az containerapp revision list -n gsd-prod-worker -g gsd-prod-rg -o table
   ```
4. **Correlate**: Run the alert KQL query manually to see exact log lines:
   ```kql
   ContainerAppConsoleLogs_CL
   | where ContainerAppName_s == "gsd-prod-worker"
   | where Log_s has "Docket worker stopped unexpectedly"
     or Log_s has "did not enter polling loop"
     or Log_s has "worker.docket.depth_failed"
   | project TimeGenerated, Log_s
   | order by TimeGenerated desc
   | take 20
   ```
5. **Resolve or escalate**: If worker is healthy now, resolve the alert. If ongoing, follow mitigations below.

## Mitigations

### Roll back revision

Use `docs/ops/ROLLBACK.md` to activate a previous healthy revision.

### Reduce load

Temporarily reduce worker concurrency or scale to stabilize while investigating.

