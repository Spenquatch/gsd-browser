# Redis Data Model

This document describes every Redis key used by `gsd-browser`, including data types,
TTL rules, back-compat behavior, and how session status is derived from task states.

---

## Key formats

### Task ownership

| Key | Type | Content | TTL | Source |
|-----|------|---------|-----|--------|
| `gsd:v1:tasks:{task_id}:owner` | STRING (JSON) | `TaskOwnershipRecord` | `pexpireat(expires_at_ms)` | `task_ownership.py` |

**Fields:** `version`, `task_id`, `tenant_id`, `subject_id`, `transport` (stdio/http),
`tool_name`, `created_at_ms`, `expires_at_ms`, `session_id`, `worker_id`.

### Session and task indexes

| Key | Type | Members | Score | TTL | Source |
|-----|------|---------|-------|-----|--------|
| `gsd:v1:tenants:{t}:subjects:{s}:sessions:z` | ZSET | session IDs | `created_at_ms` | max rule | `task_ownership.py` |
| `gsd:v1:tenants:{t}:subjects:{s}:sessions:{sid}:tasks:z` | ZSET | task IDs | `created_at_ms` | max rule | `task_ownership.py` |

**Max rule:** `new_expiry = max(current_key_expiry, new_member_expiry)`. This prevents the
index from expiring while newer members still exist. Applied via `pexpireat` in
`TaskOwnershipStore.write()`.

### Artifact metadata

| Key | Type | Content | TTL | Source |
|-----|------|---------|-----|--------|
| `gsd:v1:artifacts:{artifact_id}:meta` | STRING (JSON) | `ArtifactIndexRecord` | `pexpireat(created_at_ms + retention_ms)` | `artifact_index.py` |

**Fields:** `version`, `state` (pending/ready), `artifact_id`, `artifact_kind`
(screenshot/run_event_chunk), `tenant_id`, `subject_id`, `session_id`, `created_at_ms`,
`content_type`, `size_bytes`, `has_error`, `screenshot_type` (agent_step/stream_sample),
`step`, `page_url`, `s3_bucket`, `s3_key`, `sha256_hex`, `artifact_backend` (s3/azure/redis).

**State transitions:** pending (on create) -> ready (after successful upload). Pending
artifacts older than 10 minutes are treated as orphaned by the cleanup runner.

### Artifact indexes

| Key | Type | Members | Score | TTL | Source |
|-----|------|---------|-------|-----|--------|
| `gsd:v1:tenants:{t}:subjects:{s}:sessions:{sid}:screenshots:z` | ZSET | artifact IDs | `created_at_ms` | cleanup runner | `artifact_index.py` |
| `gsd:v1:tenants:{t}:subjects:{s}:sessions:{sid}:run_events:z` | ZSET | artifact IDs | `created_at_ms` | cleanup runner | `artifact_index.py` |

These ZSETs have no explicit TTL. Orphaned entries (where the meta key has expired) are
removed by the cleanup runner via `_cleanup_zsets_without_meta()`.

### Redis blob storage (fallback)

| Key | Type | Content | TTL | Source |
|-----|------|---------|-----|--------|
| `gsd:v1:artifacts:{artifact_id}:blob` | STRING (binary) | Raw image bytes | `pexpireat(created_at_ms + retention_ms)` | `screenshot_artifacts.py` |

Only used when neither Azure Blob nor S3 is configured.

### Job records

| Key | Type | Content | TTL | Source |
|-----|------|---------|-----|--------|
| `gsd:v1:jobs:{job_id}:record` | STRING (JSON) | `JobRecord` | `pexpireat(expires_at_ms)` | `job_store.py` |
| `gsd:v1:jobs:task_keys:{task_key}` | STRING | job_id | `pexpireat(expires_at_ms)` | `job_store.py` |

The reverse-lookup key maps an internal Docket task key to the public job ID.

### Maintenance

| Key | Type | Content | TTL | Source |
|-----|------|---------|-----|--------|
| `gsd:v1:maintenance:cleanup:lock` | STRING | UUID token | `px=(cleanup_interval_s * 1000) - 5000` | `artifact_index.py` |

Acquired with `NX` to ensure only one cleanup runner executes at a time.

---

## Retention and TTL rules

### Environment-aware defaults

| Environment | Default | Env var |
|-------------|---------|---------|
| dev | 86,400 s (1 day) | `GSD_RETENTION_SECONDS_DEV` |
| prod | 604,800 s (7 days) | `GSD_RETENTION_SECONDS_PROD` |

Detected via `GSD_DEPLOYMENT_ENV` (defaults to `dev`).

### TTL application by key type

- **Ownership records:** absolute `pexpireat` from the record's `expires_at_ms` (set by caller).
- **Session/task index ZSETs:** max rule ensures the index outlives all its members.
- **Artifact meta + blob keys:** `created_at_ms + (retention_seconds * 1000)`.
- **Job records + reverse index:** same as artifact retention.
- **Cleanup lock:** lease duration slightly shorter than the cleanup interval.

### Cleanup runner

Runs every `GSD_CLEANUP_INTERVAL_S` seconds (default 300). Phases:

1. Scan `gsd:v1:artifacts:*:meta` keys.
2. Delete orphaned pending artifacts (pending > 10 min): blob + meta + ZSET entry.
3. Delete expired ready artifacts: blob + meta + ZSET entry.
4. Scan screenshot/run_event ZSETs for entries whose meta key no longer exists; remove them.

Blob deletion routes by `artifact_backend`: azure -> `AzureBlobClient.delete()`,
s3 -> S3 client, redis -> `DEL` on blob key. "Not found" errors are tolerated.

---

## Session status derivation

Session status is computed from task states in two steps.

### Step 1: Task state extraction

`_task_state_from_runs_hash()` in `management_api/app.py` reads the Docket runs hash:

| Raw state (from Docket) | Mapped state |
|--------------------------|--------------|
| `running` | `running` |
| `completed` | `completed` |
| `failed` | `failed` |
| `cancelled` | `cancelled` |
| anything else / missing | `queued` |

### Step 2: Session-level aggregation

All task states within a session are collected into a set, then:

| Condition | Session status | Meaning |
|-----------|----------------|---------|
| set contains `running` | `active` | At least one task is executing |
| set contains `queued` (no running) | `create` | Tasks are queued but none running |
| all other (completed/failed/cancelled) | `terminated` | All tasks are done |

This logic is identical in both `_sessions_payload_indexed()` and `_sessions_payload_scan()`.

### Last activity timestamp

`last_activity_at` = max of all task timestamps (earliest of `completed_at`, `started_at`,
or `created_at_ms` converted to seconds). `created_at` = min task creation time in session.

---

## Back-compat and legacy inference

### Missing session index (pre-migration data)

If no session ZSET exists for an identity, the management API falls back to a global
`SCAN` over `gsd:v1:tasks:*:owner` keys. This is O(all tasks) and degrades gracefully
during migration. Once indexes are populated, the indexed path is used automatically.

### Missing `artifact_backend` field

Records created before the `artifact_backend` field was added use inference:

```
artifact_backend is set   -> use it directly
artifact_backend is null:
  s3_bucket == "redis"    -> redis backend
  s3_bucket == anything   -> s3 backend (default)
```

This is implemented in `ArtifactIndexRecord.get_effective_backend()`.

### Artifact delivery by backend

- **Azure/S3:** presigned URL returned to client (`GSD_PRESIGNED_URL_TTL_S`, default 900s).
- **Redis (legacy):** raw bytes returned inline as base64 when `include_data` is requested.
