# GSD MCP Tool API (contract)

This document is the source of truth for the `gsd` MCP tool surface.

## Versioning policy
- Every structured tool response **must** include a `version` string (for example
  `gsd.web_eval_agent.v1`) inside a single JSON payload encoded in a `TextContent`.
- Backward-compatible additions are allowed within a `vN` payload.
- Any breaking change (renames, type changes, removing fields, changing semantics) requires a new
  `version` value and (if needed) dual-reading support in clients.

## Long-running task execution (SEP-1686)
Some tools are long-running and are executed via MCP tasks (`taskSupport="required"`).
At the MCP protocol layer:
- Initial `tools/call` returns a `Task` (`taskId`, `status`, `pollInterval`, …).
- Clients use `tasks/get` + `tasks/result` (+ optional `tasks/cancel`) to retrieve status/results.

The “tool result payload” schemas below describe the **task result** payloads.

## Tools

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
  - Optional keys:
    - `page`: `{ url: string|null, title: string|null }`
    - `errors_top`: object[]
    - `timeouts`: object
    - `warnings`: string[]
    - `dev_excerpts`: object (only when `mode="dev"`)

### `web_task_agent` (task required)
Same input shape and output schema as `web_eval_agent`, but with:
- `version`: `"gsd.web_task_agent.v1"`
- `tool`: `"web_task_agent"` (added by wrapper)

### `web_task_agent_github` (task required)
Same input shape and output schema as `web_eval_agent`, but with:
- `version`: `"gsd.web_task_agent_github.v1"`
- `tool`: `"web_task_agent_github"` (added by wrapper)

### `get_run_events` (sync)
**Input**
- `session_id` (string|null, optional)
- `last_n` (integer, optional, default 50, max 200)
- `event_types` (string[]|null, optional; subset of `["agent","console","network"]`)
- `from_timestamp` (number|string|null, optional; epoch seconds or ISO-8601)
- `has_error` (bool|null, optional)
- `include_details` (bool, optional, default false)

**Output** (`TextContent[]`, exactly 1 item)
- JSON payload schema `gsd.get_run_events.v1`:
  - `version`: `"gsd.get_run_events.v1"`
  - `session_id`: string|null
  - `events`: object[]
  - `stats`: `{ counts: {agent:number, console:number, network:number, total:number}, oldest_timestamp:number|null, newest_timestamp:number|null }`
  - `error`: string|null

### `get_screenshots` (sync; phased delivery)
This tool supports phased delivery (inline now, pre-signed URLs later). The response always includes
stable IDs/metadata suitable for switching delivery mode.

**Input**
- `last_n` (integer, optional, default 5, max 20)
- `screenshot_type` (`"agent_step" | "stream_sample" | "all"`, optional, default `"agent_step"`)
- `session_id` (string|null, optional)
- `from_timestamp` (number|null, optional; epoch seconds)
- `has_error` (bool|null, optional)
- `include_images` (bool, optional, default true)

**Output** (`(TextContent|ImageContent)[]`, 1+ items)
- First item is a `TextContent` JSON payload schema `gsd.get_screenshots.v1`:
  - `version`: `"gsd.get_screenshots.v1"`
  - `session_id`: string|null (echo of filter)
  - `filters`: object (echo of applied filters)
  - `screenshots`: array of screenshot metadata objects, each with:
    - `id`, `timestamp`, `type`, `session_id`, `has_error`, `mime_type`, `url`, `step`, `metadata`
    - `artifact`: `{ key: string|null, url: string|null }` (url may be null in Phase 1)
  - `stats`: object
  - `error`: string|null
- When `include_images=true`, the response may include `ImageContent` items after the JSON header for
  screenshots that have image bytes. These are compatibility-only; the canonical metadata lives in
  the JSON header.

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
  - `next_actions`: string[]

