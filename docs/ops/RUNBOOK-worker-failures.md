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

## Mitigations

### Roll back revision

Use `docs/ops/ROLLBACK.md` to activate a previous healthy revision.

### Reduce load

Temporarily reduce worker concurrency or scale to stabilize while investigating.

