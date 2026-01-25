# GSD MCP Tool API (contract)

This document is the source of truth for the `gsd` MCP tool surface.

Canonical spec (tasks/artifacts/authZ/progress/codes/config): `gsd-browser/docs/api/FAST_MCP_V2_CANONICAL_SPEC.md`.

## Versioning policy
- Every structured tool response **must** include a `version` string (for example
  `gsd.web_eval_agent.v1`) inside a single JSON payload encoded in a `TextContent`.
- Backward-compatible additions are allowed within a `vN` payload.
- Clients **must ignore unknown keys** anywhere in the payload (forward compatibility).
- Any breaking change (renames, type changes, removing fields, changing semantics) requires a new
  `version` value and (if needed) dual-reading support in clients.

## Long-running task execution (SEP-1686)
Some tools are long-running and are executed via MCP tasks (`taskSupport="required"`).
At the MCP protocol layer:
- Initial `tools/call` returns a `Task` (`taskId`, `status`, `pollInterval`, …).
- Clients use `tasks/get` + `tasks/result` (+ optional `tasks/cancel`) to retrieve status/results.

The “tool result payload” schemas below describe the **task result** payloads.

## Tools (implemented)

### `web_eval_agent` (task required)
**Input**
- `url` (string, required): URL (scheme optional; normalized to https:// if missing)
- `task` (string, required)
- `headless_browser` (bool, optional, default `false`)
- `mode` (`"compact" | "dev"`, optional; default chosen by URL host)
- `budget_s` (number, optional; must be > 0 if set)
- `max_steps` (integer, optional; must be > 0 if set)
- `step_timeout_s` (number, optional; must be > 0 if set)

**Output** (`TextContent[]`, exactly 1 item)
- `TextContent.type` is `"text"`
- `TextContent.text` is JSON with schema `gsd.web_eval_agent.v1`:
  - Required keys:
    - `version`: `"gsd.web_eval_agent.v1"`
    - `session_id`: UUID string
    - `tool_call_id`: UUID string
    - `url`: normalized URL string
    - `task`: string
    - `mode`: `"compact" | "dev" | null`
    - `status`: `"success" | "failed" | "partial"`
    - `result`: string | null
    - `summary`: string (<= 2048 chars)
    - `artifacts`: object (counts)
    - `next_actions`: string[]
  - Additional keys (present on success and most failures; treat as stable):
    - `page`: `{ url: string|null, title: string|null }`
    - `errors_top`: array of ranked failures:
      - each item:
        `{ type, code?: string|null, summary, step: number|null, url: string|null }`
      - `step` and `url` keys are always present (may be `null`).
      - `type` taxonomy (stable):
        - `"console"`: browser console error (JS/runtime)
        - `"network"`: HTTP/network failure (4xx/5xx/timeout)
        - `"agent"`: agent loop failure (planning/step execution)
        - `"provider"`: LLM/provider error (rate limit, auth, invalid response)
        - `"validation"`: invalid inputs / contract violations detected server-side
        - `"timeout"`: time budget exceeded (tool or step)
        - `"cancelled"`: task cancelled by client/operator
      - `code` is a short machine-readable string (recommended) that remains stable across
        wording changes in `summary` (examples: `"NETWORK_HTTP_5XX"`, `"TASK_CANCELLED"`).
      - Canonical code vocabulary is in `gsd-browser/docs/api/FAST_MCP_V2_CANONICAL_SPEC.md` (§7).
    - `timeouts`:
      - `{ budget_s: number|null, step_timeout_s: number|null, max_steps: number|null, timed_out: boolean }`
    - `warnings`: string[] (bounded)
    - `requested_mode`: string|null (echo of user-provided `mode` when `mode` is `null`)
  - `dev_excerpts` (only when `mode="dev"`):
    - `{ console_errors: object[], network_errors: object[], errors_top: object[] }`

### `web_task_agent` (task required)
Same input shape and output schema as `web_eval_agent`, but with:
- `version`: `"gsd.web_task_agent.v1"`
- `tool`: `"web_task_agent"` (added by wrapper)

### `web_task_agent_github` (task required)
Same input shape and output schema as `web_eval_agent`, but with:
- `version`: `"gsd.web_task_agent_github.v1"`
- `tool`: `"web_task_agent_github"` (added by wrapper)

### `web_eval_agent_submit` (sync; compat job submit)
Submit `web_eval_agent` work for clients that do not implement SEP-1686 tasks.

**Input**
- Same input shape as `web_eval_agent` (without SEP-1686 task metadata).

**Output** (`TextContent[]`, exactly 1 item)
- JSON payload schema `gsd.job_submit.v1`:
  - `version`: `"gsd.job_submit.v1"`
  - `job_id`: UUID string|null
  - `tool_name`: string
  - `state`: `"queued"`
  - `session_id`: UUID string|null
  - `created_at`: number|null (epoch seconds)
  - `expires_at`: number|null (epoch seconds)
  - `error`: `{code:string, message:string, details:object|null} | null`

### `web_task_agent_submit` (sync; compat job submit)
Same as `web_eval_agent_submit`, but submits `web_task_agent` work.

**Input**
- Same input shape as `web_task_agent`.

**Output**
- `gsd.job_submit.v1`

### `web_task_agent_github_submit` (sync; compat job submit)
Same as `web_eval_agent_submit`, but submits `web_task_agent_github` work.

**Input**
- Same input shape as `web_task_agent_github`.

**Output**
- `gsd.job_submit.v1`

### `job_get` (sync; compat job status snapshot)
**Input**
- `job_id` (string, required; UUID)

**Output** (`TextContent[]`, exactly 1 item)
- JSON payload schema `gsd.job_get.v1`:
  - `version`: `"gsd.job_get.v1"`
  - `job_id`: UUID string|null (echo of input)
  - `found`: boolean
  - `tool_name`: string|null
  - `state`: `"queued" | "running" | "completed" | "failed" | "cancelled" | null`
  - `progress_message`: string (always present; empty when `found=false`)
  - `progress`: `{current:int, total:int, percentage:float} | null`
  - `session_id`: UUID string|null
  - `created_at`: number|null (epoch seconds)
  - `started_at`: number|null (epoch seconds)
  - `updated_at`: number|null (epoch seconds)
  - `finished_at`: number|null (epoch seconds)
  - `expires_at`: number|null (epoch seconds)
  - `error`: `{code:string, message:string, details:object|null} | null`

Non-enumerability:
- If the job does not exist or is owned by a different tenant/subject, return `found=false` and `error=null`.

### `get_run_events` (sync)
**Input**
- `session_id` (UUID string, required)
- `last_n` (integer, optional, default 50, max 200)
- `event_types` (string[]|null, optional; subset of `["agent","console","network"]`)
- `from_timestamp` (number|string|null, optional; epoch seconds or ISO-8601)
- `has_error` (bool|null, optional)
- `include_details` (bool, optional, default false)

**Output** (`TextContent[]`, exactly 1 item)
- JSON payload schema `gsd.get_run_events.v1`:
  - `version`: `"gsd.get_run_events.v1"`
  - `session_id`: UUID string|null (echo of filter; null on validation errors)
  - `events`: object[]
  - `stats`: `{ counts: {agent:number, console:number, network:number, total:number}, oldest_timestamp:number|null, newest_timestamp:number|null }` (timestamps are epoch seconds)
  - `error`: string|null
Non-enumerability:
- If the session has no visible events to the caller (nonexistent or owned by a different tenant/subject),
  return `events=[]` and `error=null`.
Invalid input:
- If any filter is invalid (including invalid `from_timestamp`), return `events=[]` and a non-null `error`.

### `get_screenshots` (sync; phased delivery)
This tool supports phased delivery (inline now, pre-signed URLs later). The response always includes
stable IDs/metadata suitable for switching delivery mode.

**Input**
- `last_n` (integer, optional, default 5, max 20)
- `screenshot_type` (`"agent_step" | "stream_sample" | "all"`, optional, default `"agent_step"`)
- `session_id` (UUID string, required)
- `from_timestamp` (number|null, optional; epoch seconds)
- `has_error` (bool|null, optional)
- `include_images` (bool, optional, default true)

**Output** (`(TextContent|ImageContent)[]`, 1+ items)
- First item is a `TextContent` JSON payload schema `gsd.get_screenshots.v1`:
  - `version`: `"gsd.get_screenshots.v1"`
  - `session_id`: UUID string|null (echo of filter; null on validation errors)
  - `filters`: object (echo of applied filters)
  - `screenshots`: array of screenshot metadata objects, each with:
    - `id`, `timestamp`, `type`, `session_id`, `has_error`, `mime_type`, `url`, `step`, `metadata`
    - `timestamp` is epoch seconds (float)
    - `inline_included`: boolean (required; never null). When `true`, an inline `ImageContent` item is included.
    - `url` is the **page URL** that the screenshot was captured from (not an artifact URL).
    - `artifact` (presigned-url-ready):
      - `key`: UUID string (required; stable artifact id). Always equals `id`.
      - `url`: string|null (artifact URL; typically null in Phase 1, pre-signed in Phase 2)
      - `content_type`: string|null
      - `size_bytes`: integer|null
      - `created_at`: number|null (epoch seconds)
      - `url_expires_at`: number|null (epoch seconds)
  - `stats`: object
  - `error`: string|null
- When `include_images=true`, the response may include `ImageContent` items after the JSON header for
  screenshots that have image bytes. These are compatibility-only; the canonical metadata lives in
  the JSON header.
Non-enumerability:
- If the session has no visible screenshots to the caller (nonexistent or owned by a different tenant/subject),
  return `screenshots=[]` and `error=null`.
Invalid input:
- If `session_id` is missing/invalid, return `screenshots=[]` and a non-null `error`.

**Mapping JSON headers → inline `ImageContent`**
- Each screenshot header includes `inline_included` (boolean, required). When `true`, an inline
  `ImageContent` item is included for that screenshot. Clients should iterate `screenshots[]` and
  consume one image only when `inline_included=true`.
- After the JSON header `TextContent`, the response contains only `ImageContent` items (no other
  `Content` types). The number of `ImageContent` items equals the number of screenshot headers where
  `inline_included=true`, in the same order.

**Delivery mode**
- Phase 1 default: inline `ImageContent` items plus JSON header metadata.
- Phase 2 later: return `artifact.url` (pre-signed URL) for blobs and stop emitting inline images for
  large payloads.
- Controlled by env/config: `GSD_ARTIFACT_DELIVERY_MODE=inline|presigned|both`.

Delivery mode matrix (authoritative):
- `delivery_mode=inline`
  - `include_images=true`: emit inline images when bytes exist; `inline_included=true` for those; `artifact.url=null`
  - `include_images=false`: no inline images; `inline_included=false` for all; `artifact.url=null`
- `delivery_mode=presigned`
  - no inline images; `inline_included=false` for all; `artifact.url` populated
- `delivery_mode=both`
  - `include_images=true`: inline images + `artifact.url` populated
  - `include_images=false`: no inline images; `artifact.url` populated

### `setup_browser_state` (sync)
**Input**
- `url` (string|null, optional)
- `state_id` (string|null, optional)

**Output** (`TextContent[]`, exactly 1 item)
- JSON payload schema `gsd.setup_browser_state.v1`:
  - `version`: `"gsd.setup_browser_state.v1"`
  - `status`: `"success" | "failed"`
  - `state_id`: string|null
  - `url`: string|null
  - `path`: string|null
  - `summary`: string
  - `traceback`: string|null (optional; present on failures when available)
  - `next_actions`: string[]

### `tasks_list` (sync; wrapper over 8081 listing semantics)
This tool is a convenience wrapper over the shared internal ops service layer. The listing contract
is pinned by `gsd-browser/docs/api/HTTP_API.md` (`GET /api/v1/tasks`) and MUST match it.

**Input**
- `limit` (int, optional): default `100`, max `1000`
- `cursor` (string, optional): opaque pagination cursor
- `status` (string, optional): `queued|running|completed|failed|cancelled`
- `tool_name` (string, optional): comma-separated tool names (example: `web_eval_agent,web_task_agent`)
- `since` (string, optional): RFC 3339 timestamp (preferred) or duration (`30m`, `7d`)

**Output** (`TextContent[]`, exactly 1 item)
- JSON payload schema `gsd.tasks_list.v1`:
  - `version`: `"gsd.tasks_list.v1"`
  - `tasks`: array of task summary objects:
    - `task_id` (UUID string)
    - `tool_name` (string)
    - `status` (string)
    - `created_at` (RFC 3339 timestamp string)
    - `updated_at` (RFC 3339 timestamp string|null)
    - `expires_at` (RFC 3339 timestamp string)
    - `session_id` (UUID string)
  - `next_cursor` (string|null)
  - `error` (object|null): stable error payload:
    - `{ code: string, message: string, details: object|null }`

Error semantics (pinned):
- Invalid inputs (including cursor reuse across different filters) MUST return `tasks=[]` and a
  non-null `error` object (for example `code="invalid_cursor"`). See `gsd-browser/docs/api/HTTP_API.md`.

### `tasks_admin_list` (sync; wrapper over 8081 admin listing semantics)
This tool is a convenience wrapper over the shared internal ops service layer. The listing contract
is pinned by `gsd-browser/docs/api/HTTP_API.md` (`GET /api/v1/admin/tasks`) and MUST match it.

Admin gating (pinned):
- Server enablement: `GSD_ADMIN_MODE=true`
- Caller authorization (HTTP transport only): `gsd:admin` scope

**Input**
- All params from `tasks_list`, plus:
  - `tenant_id` (string, optional)
  - `subject_id` (string, optional)
  - `transport` (string, optional): `stdio|http`

**Output** (`TextContent[]`, exactly 1 item)
- JSON payload schema `gsd.tasks_admin_list.v1`:
  - `version`: `"gsd.tasks_admin_list.v1"`
  - `tasks`: array of admin task summary objects:
    - all fields from `tasks_list.tasks[]`, plus:
      - `tenant_id` (string)
      - `subject_id` (string)
      - `transport` (`"stdio"|"http"`)
  - `next_cursor` (string|null)
  - `error` (object|null): stable error payload:
    - `{ code: string, message: string, details: object|null }`

Error semantics (pinned):
- If `GSD_ADMIN_MODE` is disabled, the tool MUST return `tasks=[]` and a non-null `error` object
  (recommended `code="admin_disabled"`).
- Invalid inputs MUST return `tasks=[]` and a non-null `error` object. See `gsd-browser/docs/api/HTTP_API.md`.

## Tools (planned; not yet implemented in runtime)
These tool contracts are pinned for later implementation. Do not add them to the live tool list
until the corresponding implementation tasks are complete (see `docs/planning/FAST_MCP_V2_EXECUTION_TASKS.json`).

### Compat jobs (non-SEP-1686 clients)
Some MCP hosts do not implement SEP-1686 tasks. Compat jobs provide a synchronous tool surface for
“submit + poll + fetch + cancel” workflows while preserving non-enumerability and tenant/subject
authZ (ADR-0011; canonical invariants: `gsd-browser/docs/api/FAST_MCP_V2_CANONICAL_SPEC.md` §3.6).

State vocabulary (pinned): `queued|running|completed|failed|cancelled`.

#### `job_result` (sync; final payload when ready)
Input:
- `job_id` (string, required)

Output:
- If the job is terminal (`completed|failed|cancelled`) and visible to the caller:
  - return the final tool payload (same schema as the corresponding tool; same as `tasks/result`).
- Otherwise (including `queued|running`):
  - return a stable “not ready” payload: `gsd.job_result.not_ready.v1`:
    - `version`: `"gsd.job_result.not_ready.v1"`
    - `job_id`: UUID string|null (echo of input)
    - `found`: boolean
    - `state`: `"queued" | "running" | null`
    - `progress_message`: string (always present; empty when `found=false`)
    - `progress`: `{current:int, total:int, percentage:float} | null`
    - `error`: `{code:"NOT_READY", message:string, details:object|null} | null`

#### `job_cancel` (sync)
Input:
- `job_id` (string, required)

Output: JSON payload schema `gsd.job_cancel.v1` (in a single `TextContent`):
- `version`: `"gsd.job_cancel.v1"`
- `job_id`: UUID string|null (echo of input)
- `found`: boolean
- `state`: `"queued" | "running" | "completed" | "failed" | "cancelled" | null`
- `error`: `{code:string, message:string, details:object|null} | null`

Non-enumerability:
- If the job does not exist or is owned by a different tenant/subject, return `found=false` and `error=null`.

#### `job_wait` (sync; wait-but-don’t-cancel convenience)
Input:
- `job_id` (string, required)
- `max_wait_s` (int, optional, default `300`, max `3600`)
- `poll_interval_s` (number, optional, default `2.0`, min `0.5`)

Output:
- If the job reaches a terminal state within `max_wait_s`:
  - return the final tool payload (same schema as `job_result` success case).
- On timeout:
  - return the stable timeout payload `gsd.job_wait.timeout.v1` (ADR-0011):
    - `version`: `"gsd.job_wait.timeout.v1"`
    - `job_id`: UUID string
    - `state`: `"queued" | "running"`
    - `progress_message`: string
    - `progress`: `{current:int, total:int, percentage:float} | null`
    - `error`: `{code:"TIMEOUT", message:string, details:{max_wait_s:int}}`
