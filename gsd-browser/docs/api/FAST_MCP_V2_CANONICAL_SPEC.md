# FastMCP v2 “Option B” — Canonical Spec (no open questions)

This document is the canonical, implementation-level specification for the FastMCP v2 (“Option B”)
migration. It defines identity/authZ behavior, task persistence/keying, artifact storage + index
layout, progress conventions, diagnostic codes, and configuration.

Status/migration boundary: `gsd-browser/docs/api/STATUS.md`.

## 1) Identity model (authoritative)

All authorization decisions are made using a normalized identity:

```text
tenant_id: string
subject_id: string
transport: "stdio" | "http"
```

### 1.1 `stdio` transport identity (always)
- `tenant_id = "local"`
- `subject_id = "local"`
- `transport = "stdio"`

This is a single-tenant local trust boundary. No external authentication is performed.

### 1.2 `http` transport identity (required)
HTTP transport is only supported when JWT auth is configured. The server MUST refuse to start in
HTTP mode if the required auth config is missing.

The caller MUST send:
- `Authorization: Bearer <JWT>`

JWT verification requirements:
- Signature verification via JWKS (`GSD_JWT_JWKS_URL`)
- `iss` MUST equal `GSD_JWT_ISSUER`
- `aud` MUST contain `GSD_JWT_AUDIENCE`
- `exp` MUST be valid (no expired tokens)

Claim → identity mapping:
- `subject_id` is read from claim name `GSD_JWT_SUBJECT_ID_CLAIM` (default: `sub`)
- `tenant_id` is read from claim name `GSD_JWT_TENANT_ID_CLAIM` (default: `tenant_id`)

Constraints:
- `tenant_id` and `subject_id` MUST be non-empty strings (after trimming).
- `tenant_id` and `subject_id` MUST match regex: `^[a-zA-Z0-9][a-zA-Z0-9:_-]{0,63}$`
- Operators MUST choose claim mappings whose values satisfy the regex; otherwise tokens are rejected.
- If any requirement fails, the request is unauthorized.

### 1.3 Scope extraction (authoritative)
Scope checks (ADR-0013) rely on extracting scopes from JWT claims.

Extraction rules (pinned):
- Prefer claim `scope` (string; space-separated).
- Fallback to claim `scp`, which may be either:
  - an array of strings, or
  - a space-separated string.
- Any invalid scope claim format results in “no scopes”.

### 1.4 Clerk compatibility notes (non-normative)
Clerk should be compatible with this contract, provided the minted JWTs include the required claims.
In practice, you will likely configure a Clerk **JWT template** (or custom session token claims) so
the token matches the expectations below:

- `iss`: must match `GSD_JWT_ISSUER`.
- `aud`: must match `GSD_JWT_AUDIENCE`.
  - Note: some Clerk flows also use/mention `azp` (authorized party). This spec’s audience binding is
    expressed via `aud`; prefer configuring Clerk tokens so `aud` is present and stable.
- `sub`: subject identifier (default mapping).
- `tenant_id`: provide a top-level string claim (for example, map the active Organization ID to a
  custom `tenant_id` claim via Clerk configuration, or configure `GSD_JWT_TENANT_ID_CLAIM` to point at
  an alternate top-level claim).
- Scopes: include either `scope` (space-separated string) or `scp` (string/array) containing the
  required `gsd:*` scopes (for example `gsd:admin` for admin endpoints).

As always, `tenant_id` and `subject_id` values must satisfy the identity regex constraints in §1.2.

## 2) Authorization rules (authoritative)

### 2.1 Non-enumerability
For task and artifact access, authorization failures MUST be non-enumerable:
- Return “not found” semantics (equivalent to a 404) when the resource exists but caller is not
  authorized.

Server MUST still log an internal audit event for denied access attempts (see §2.3).

### 2.2 Tasks
`taskId` is NOT an authorization boundary.

For any `tasks/get`, `tasks/result`, `tasks/cancel` request:
- The server MUST load the TaskOwnershipRecord (see §3.2) for `task_id`.
- If no record exists, return not found.
- If record exists and `(tenant_id, subject_id)` do not match the caller, return not found.
- If record exists and matches, allow access.

### 2.3 Artifacts
`session_id` and artifact keys are NOT authorization boundaries.

Artifact list tools are tenant/subject isolated by construction:
- `get_screenshots` and `get_run_events` MUST query Redis indices that are scoped by
  `(tenant_id, subject_id, session_id)` (see §4.3).
- For these list tools, the server MUST NOT return a distinct “denied” vs “missing” response; the
  response MUST be identical for:
  - a nonexistent session, and
  - a session that exists for a different `(tenant_id, subject_id)`.

This achieves non-enumerability without requiring a separate SessionOwnershipRecord.

### 2.4 Audit logging (required)
The server MUST emit structured logs for:
- Task access denied (includes `task_id`, caller identity, and stored owner identity)
- Artifact list queries (`get_screenshots`, `get_run_events`) (includes `session_id`, filters, caller identity)
- Presigned URL issuance (includes `artifact_id`, expiry, caller identity)

## 3) Task semantics + persistence

### 3.1 Task execution mode (long tools)
These tools are task-required:
- `web_eval_agent`
- `web_task_agent`
- `web_task_agent_github`

### 3.2 Task ownership record (Redis; required)
In addition to Docket’s internal task storage, `gsd` MUST persist an ownership record for every task.

Redis key format (string keys, no spaces):
- `gsd:v1:tasks:{task_id}:owner`

Value format:
- UTF-8 JSON object (TaskOwnershipRecord), stored as a single JSON string value.

TaskOwnershipRecord schema:
```json
{
  "version": "gsd.task_ownership.v1",
  "task_id": "<uuid>",
  "tenant_id": "<tenant_id>",
  "subject_id": "<subject_id>",
  "transport": "stdio|http",
  "tool_name": "web_eval_agent|web_task_agent|web_task_agent_github",
  "created_at_ms": 1730000000000,
  "expires_at_ms": 1730000900000,
  "session_id": "<uuid>"
}
```

TTL behavior:
- The Redis key TTL MUST be set to expire at `expires_at_ms`.
- On task completion, the TTL remains unchanged (ownership remains valid until expiry).

Task ownership record atomicity:
- The server MUST persist the TaskOwnershipRecord before returning a `Task` response to the client.
- If writing the TaskOwnershipRecord fails:
  - the tool call MUST fail (no `Task` returned to the client)
  - the server MUST attempt to cancel the created task (best effort)
  - the server MUST emit an audit log entry with the failure cause and the intended owner identity

### 3.3 TTL policy (server-controlled)
Server-side defaults and bounds are server-controlled and configurable via env:
- `web_eval_agent`: 900 seconds
- `web_task_agent`: 1800 seconds
- `web_task_agent_github`: 1800 seconds
- Minimum TTL: 60 seconds
- Maximum TTL: 7200 seconds

Client-provided TTL override:
- Allowed ONLY when `GSD_TASK_ALLOW_CLIENT_TTL_OVERRIDE=true`
- Override MUST be clamped by rejection (not clamping):
  - if requested TTL < min or > max → reject the call

MCP protocol unit conversion:
- MCP `task.ttl` and `Task.pollInterval` are **milliseconds**.
- All `_S` environment/config values in `gsd` are **seconds** and MUST be converted to milliseconds
  at the MCP protocol boundary.
- `GSD_TASK_POLL_INTERVAL_MS` is already milliseconds and MUST be passed through as-is.

### 3.4 Poll interval
Server MUST set `Task.pollInterval = GSD_TASK_POLL_INTERVAL_MS` (milliseconds; default 2000) for
these task-required tools.

### 3.5 Cancellation (cooperative; required)
Cancellation is cooperative and MUST be enforced by the tool implementation:
- On `tasks/cancel`, the task MUST transition to cancelled status promptly.
- The running tool MUST check for cancellation between agent steps and must stop work when cancelled.
- The tool MUST release resources in `finally` blocks (close pages/contexts; stop streaming).

## 4) Artifact storage + index

### 4.1 Artifact kinds
`gsd` persists two artifact families for session-scoped tools:
- screenshots (binary images)
- run events (JSONL or JSON)

### 4.2 S3 object key scheme (required)
All object keys MUST be tenant-prefixed and subject-scoped:
- `tenants/{tenant_id}/subjects/{subject_id}/sessions/{session_id}/...`

Screenshot object key format:
- `tenants/{tenant_id}/subjects/{subject_id}/sessions/{session_id}/screenshots/{timestamp_ms}_{screenshot_id}.png`

Run events object key format:
- `tenants/{tenant_id}/subjects/{subject_id}/sessions/{session_id}/run-events/{timestamp_ms}_{chunk_id}.jsonl`

Encryption:
- Encryption-at-rest MUST be enabled. Server behavior is controlled by `GSD_S3_SSE_MODE`:
  - `sse_s3`: server MUST set SSE-S3 header `x-amz-server-side-encryption: AES256` on all PUTs
  - `none`: server MUST NOT set any SSE headers; deployment MUST still ensure encryption-at-rest

### 4.3 Redis index (required)
Redis is the authoritative index for listing/filtering. S3 is treated as blob storage.

Artifact ID format:
- UUID string (v4)

ID validation:
- `task_id`, `session_id`, and `artifact_id` MUST be canonical UUIDv4 strings.
- Any request containing a non-UUID value in a position that is used in Redis key construction MUST
  be rejected.

Metadata key:
- `gsd:v1:artifacts:{artifact_id}:meta` → JSON (ArtifactIndexRecord)

Session listing keys:
- screenshots: `gsd:v1:tenants:{tenant_id}:subjects:{subject_id}:sessions:{session_id}:screenshots:z`
- run events: `gsd:v1:tenants:{tenant_id}:subjects:{subject_id}:sessions:{session_id}:run_events:z`

Sorted set members and scores:
- member: `artifact_id`
- score: `timestamp_ms` (integer)

ArtifactIndexRecord schema:
```json
{
  "version": "gsd.artifact_index.v1",
  "state": "pending|ready",
  "artifact_id": "<uuid>",
  "artifact_kind": "screenshot|run_event_chunk",
  "tenant_id": "<tenant_id>",
  "subject_id": "<subject_id>",
  "session_id": "<uuid>",
  "created_at_ms": 1730000000000,
  "content_type": "image/png",
  "size_bytes": 12345,
  "has_error": false,
  "screenshot_type": "agent_step|stream_sample|null",
  "step": 12,
  "page_url": "https://example.com",
  "s3_bucket": "<bucket>",
  "s3_key": "tenants/.../screenshots/...",
  "sha256_hex": "<hex|null>"
}
```

Artifact write atomicity (S3 + Redis):
- Artifact creation MUST follow this sequence:
  1) Write Redis metadata key `...:meta` with `state="pending"` and all identity + S3 location fields.
  2) Upload the object to S3 using the target `s3_key`.
  3) Finalize Redis by setting `state="ready"` and adding `artifact_id` to the session zset.
- If step (1) fails: the artifact MUST NOT be uploaded to S3.
- If step (2) fails: the server MUST delete the Redis metadata key and MUST NOT add any zset member.
- If step (3) fails: the server MUST leave `state="pending"` and MUST emit an audit log; cleanup MUST
  treat old pending artifacts as orphaned and delete them (see Cleanup rules).

Index TTL/retention:
- Default retention is environment-driven and MUST be applied consistently to:
  - S3 objects (deletion)
  - Redis metadata keys
  - Redis sorted set members
- Retention defaults:
  - `dev`: 86400 seconds (24h)
  - `prod`: 604800 seconds (7d)

Cleanup rules (required):
- Leadership: in multi-replica deployments, only one instance MUST run cleanup at a time using a
  Redis distributed lock:
  - lock key: `gsd:v1:maintenance:cleanup:lock`
  - acquisition: `SET <key> <uuid> NX PX <lease_ms>`
  - lease: `lease_ms = GSD_CLEANUP_INTERVAL_S * 1000 - 5000` (minimum 10000ms)
  - release: the lock holder MUST NOT delete the lock key; it MUST rely on TTL expiry (no `DEL`)
  - only the lock holder performs cleanup for that interval
- Idempotency and partial failure handling:
  - If S3 delete returns 404/NoSuchKey, treat as success and remove Redis entries.
  - If Redis meta is missing but zset member exists, remove the zset member.
  - If Redis meta exists but zset member is missing, leave meta and allow it to expire by TTL.
  - If S3 delete fails transiently, do not remove the Redis meta/zset member; retry on next cycle.
- Pending artifacts:
  - Any artifact with `state="pending"` older than 10 minutes MUST be treated as orphaned and deleted
    from S3, then removed from Redis.

### 4.4 Presigned URL policy (Phase 2 contract; required)
Presigned URLs MUST be generated only after authorization succeeds.

Constraints:
- Method: GET only
- Expiration:
  - default: 900 seconds
  - maximum: 3600 seconds (server MUST reject larger values)
- Returned fields:
  - `artifact.url` is the presigned URL
  - `artifact.url_expires_at` is epoch seconds (float)

Browser completeness requirements:
- The object store MUST be configured with CORS that allows browser-based clients to fetch artifacts:
  - Allowed methods: `GET`, `HEAD`
  - Allowed headers: `*`
  - Exposed headers: `Content-Type`, `Content-Length`, `ETag`, `Last-Modified`
  - Allowed origins: the operator UI origin(s) for the deployment

Caching policy (portable across S3-compatible stores):
- On upload, the server MUST set object metadata `Cache-Control: no-store`.

Clients refresh behavior:
- Clients MUST re-call retrieval tools to obtain fresh URLs after expiration.

## 5) Tool listing semantics (authoritative)

Timestamp units (tool payloads):
- All timestamps in JSON tool payloads are epoch seconds (float).
- Internal indices and object keys may use milliseconds (e.g., zset scores and S3 key prefixes).

### 5.1 `get_screenshots` ordering and pairing
Ordering:
- Results are ordered newest → oldest.

Pagination:
- `last_n` is a hard maximum of 20.

Filtering:
- `session_id` MUST be provided and restricts listing to that session.
- `from_timestamp` is epoch seconds; server converts to `timestamp_ms` and filters by score.
- `has_error` filters based on ArtifactIndexRecord.has_error.
- `screenshot_type` filters based on ArtifactIndexRecord.screenshot_type.

Non-enumerability (list semantics):
- If the session has no visible artifacts to the caller (nonexistent or owned by a different
  `(tenant_id, subject_id)`), the server MUST return:
  - `screenshots=[]`
  - `error=null`
  - `session_id` MUST echo the filter value (UUID), since this response shape is indistinguishable
    from a valid-but-empty session.

Invalid input:
- If `session_id` is missing or invalid, the server MUST return:
  - `session_id=null`
  - `screenshots=[]`
  - `error` as a non-null validation message string
  - no inline `ImageContent` items

Identity and stable IDs:
- `screenshots[].id` MUST be a UUIDv4 string and is the stable artifact identifier for that screenshot.
- `screenshots[].artifact.key` MUST equal `screenshots[].id`.

Delivery mode matrix (authoritative):
- Delivery mode is controlled by `GSD_ARTIFACT_DELIVERY_MODE` and request `include_images`.
- For all modes, the JSON header is always present and contains canonical metadata.
- Outcomes:
  - `delivery_mode=inline`
    - `include_images=true`: emit inline `ImageContent` where bytes exist; set `inline_included=true` for those; `artifact.url=null`
    - `include_images=false`: emit no inline images; set `inline_included=false` for all; `artifact.url=null`
  - `delivery_mode=presigned`
    - always emit no inline images; set `inline_included=false` for all
    - set `artifact.url` + `artifact.url_expires_at` for each screenshot artifact
  - `delivery_mode=both`
    - `include_images=true`: emit inline images (as in `inline`) and also set `artifact.url` + `artifact.url_expires_at`
    - `include_images=false`: emit no inline images; set `inline_included=false` for all; set `artifact.url` + `artifact.url_expires_at`
- Presign failures:
  - If presigning fails for any artifact, the server MUST:
    - set that artifact’s `artifact.url=null` and `artifact.url_expires_at=null`
    - set the top-level `error` to a non-null summary string
    - emit a structured log with the failure cause

Inline image pairing (deterministic):
- Each screenshot header includes `inline_included` (server output MUST always be `true` or `false`):
  - `true` when inline image bytes are included in the response as an `ImageContent`
  - `false` when no inline image is included for that screenshot
- After the JSON header `TextContent`, the response MUST contain only `ImageContent` items.
- Let `K = count(screenshots[].inline_included == true)`. The response MUST contain exactly `K`
  `ImageContent` items, in the same order as the corresponding `screenshots[]` headers.
- Clients MUST iterate `screenshots[]` and consume one `ImageContent` item only when
  `inline_included=true`.

### 5.2 `get_run_events` ordering and chunking
Ordering:
- Run event chunks are ordered newest → oldest.

Chunk format:
- Each run-event artifact is a JSON Lines payload (`.jsonl`) where each line is one event object.

Filtering:
- `session_id` MUST be provided and restricts listing to that session.
- `event_types` MAY be provided; when provided it MUST be a subset of `["agent","console","network"]`.
- `has_error` MAY be provided; when provided it filters events where `has_error` matches.
- `from_timestamp` MAY be provided; when provided it MUST be either:
  - epoch seconds (number), or
  - ISO-8601 timestamp string.
- `include_details` defaults to `false`; when `false`, the server MUST omit heavy event detail payloads.
- `last_n` defaults to 50 and applies after filtering (hard maximum 200).

Non-enumerability (list semantics):
- If the session has no visible events to the caller (nonexistent or owned by a different
  `(tenant_id, subject_id)`), the server MUST return:
  - `events=[]`
  - `error=null`
  - `session_id` MUST echo the filter value (UUID), since this response shape is indistinguishable
    from a valid-but-empty session.

Invalid input handling:
- If any provided filter is invalid (including `event_types` outside the allowed subset or an invalid
  `from_timestamp`), the server MUST return:
  - `events=[]`
  - `session_id=null`
  - `error` as a non-null validation message string

## 6) Progress reporting conventions

Progress notifications MUST be emitted:
- once at task start
- at least once per agent step
- once on completion/cancellation/failure

Progress unit rules:
- If `max_steps` is known: use step-based progress
  - `progress = steps_completed`
  - `total = max_steps`
- If `max_steps` is unknown:
  - `progress = 0`
  - `total = 0`
  - message MUST still describe phase

Message format (string; stable prefix keys):
```text
phase=<init|navigate|agent_step|finalize|done|cancelled|failed> step=<n|null> note=<free text>
```

Progress message bounds:
- `note` MUST be at most 200 characters.

## 7) Diagnostic `code` vocabulary (stable)

`errors_top[].code` values MUST come from this table.

| `type` | `code` | Meaning |
| --- | --- | --- |
| `network` | `NETWORK_HTTP_4XX` | HTTP response status 4xx |
| `network` | `NETWORK_HTTP_5XX` | HTTP response status 5xx |
| `network` | `NETWORK_TIMEOUT` | Network request timed out |
| `network` | `NETWORK_DNS` | DNS resolution failure |
| `provider` | `PROVIDER_RATE_LIMIT` | LLM provider rate limiting |
| `provider` | `PROVIDER_AUTH` | LLM provider auth/permission failure |
| `provider` | `PROVIDER_BAD_RESPONSE` | Provider returned invalid/unparseable response |
| `agent` | `AGENT_STEP_FAILED` | Agent step failed (tool/action execution) |
| `agent` | `AGENT_PLAN_FAILED` | Agent planning failed |
| `validation` | `VALIDATION_INPUT` | Invalid tool input parameters |
| `validation` | `VALIDATION_OUTPUT` | Output could not be validated / contract violation |
| `timeout` | `TIMEOUT_BUDGET` | Overall tool budget exceeded |
| `timeout` | `TIMEOUT_STEP` | Step timeout exceeded |
| `cancelled` | `TASK_CANCELLED` | Task was cancelled by caller |
| `console` | `CONSOLE_ERROR` | Browser console error logged |

## 8) Configuration (single source of truth)

All configuration is via environment variables.

### 8.1 Deployment mode
- `GSD_DEPLOYMENT_ENV` (string): MUST be `dev` or `prod` (default: `dev`)

### 8.2 Transport
- `GSD_TRANSPORT` (string): MUST be `stdio` or `http`
  - if `stdio`: server starts stdio transport only
  - if `http`: server starts HTTP transport only and requires JWT auth config

### 8.3 JWT auth (required for `GSD_TRANSPORT=http`)
- `GSD_JWT_JWKS_URL` (string; required)
- `GSD_JWT_ISSUER` (string; required)
- `GSD_JWT_AUDIENCE` (string; required)
- `GSD_JWT_TENANT_ID_CLAIM` (string; default: `tenant_id`)
- `GSD_JWT_SUBJECT_ID_CLAIM` (string; default: `sub`)

### 8.4 Tasks (required for Option B)
- `FASTMCP_DOCKET_URL` (string; required): MUST be `redis://...` (no `memory://`)
  - All Redis usage (task ownership, artifact indexing, maintenance locks) uses this single Docket
    Redis backend. There is no separate `GSD_REDIS_URL`; a single Redis instance (or cluster)
    satisfies all requirements.
- `GSD_TASK_ALLOW_CLIENT_TTL_OVERRIDE` (bool; default: `false`)
- `GSD_TASK_TTL_MIN_S` (int; default: `60`)
- `GSD_TASK_TTL_MAX_S` (int; default: `7200`)
- `GSD_TASK_TTL_WEB_EVAL_AGENT_S` (int; default: `900`)
- `GSD_TASK_TTL_WEB_TASK_AGENT_S` (int; default: `1800`)
- `GSD_TASK_TTL_WEB_TASK_AGENT_GITHUB_S` (int; default: `1800`)
- `GSD_TASK_POLL_INTERVAL_MS` (int; default: `2000`)

### 8.5 Artifact delivery
- `GSD_ARTIFACT_DELIVERY_MODE` (string): MUST be `inline` or `presigned` or `both` (default: `inline`)
- `GSD_PRESIGNED_URL_TTL_S` (int; default: `900`, max: `3600`)

### 8.6 S3 artifact store (required for distributed artifact persistence)
`gsd` supports AWS S3 and S3-compatible object stores; the self-hosted reference deployment is
SeaweedFS (via its S3 gateway). See `docs/adr/ADR-0009-distributed-artifact-storage-for-scaled-tasks.md`.

- Without these settings, `gsd` may still run and return inline artifacts, but artifacts are not
  durably persisted to shared storage for cross-process/replica retrieval.
- `GSD_S3_ENDPOINT_URL` (string; required for persistence)
- `GSD_S3_BUCKET` (string; required for persistence)
- `GSD_S3_REGION` (string; required for persistence)
- `GSD_S3_ACCESS_KEY_ID` (string; required for persistence)
- `GSD_S3_SECRET_ACCESS_KEY` (string; required for persistence)
- `GSD_S3_SSE_MODE` (string): MUST be `sse_s3` or `none` (default: `sse_s3`)

### 8.7 Retention/cleanup
- `GSD_RETENTION_SECONDS_DEV` (int; default: `86400`)
- `GSD_RETENTION_SECONDS_PROD` (int; default: `604800`)
- `GSD_CLEANUP_INTERVAL_S` (int; default: `300`)
