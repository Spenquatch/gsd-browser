# O2b – `get_run_events` tool + response modes (compact vs dev)

## Scope
- Add MCP tool `get_run_events` to retrieve stored run events without bloating `web_eval_agent`.
- Add response mode selection to `web_eval_agent`:
  - `compact`: minimal summary + `result` + references (default for non-localhost).
  - `dev`: includes bounded excerpts of console/network issues (top errors) to support web development workflows (default for localhost/127.0.0.1).
  - Explicit argument overrides default.
- Preserve prior dev workflow value:
  - The LLM should still get enough signal to debug quickly (errors + failed requests), without the full firehose.

## `get_run_events` API (MCP compliant, JSON text)
Parameters:
- `session_id` (optional)
- `last_n` (default 50, max 200)
- `event_types` (optional): `["agent", "console", "network"]`
- `from_timestamp` (optional)
- `has_error` (optional)
- `include_details` (bool, default false)

Return:
- `list[TextContent]` with one JSON payload:
  - `version`: `"gsd-browser.get_run_events.v1"`
  - `session_id`
  - `events` (bounded array)
  - `stats` (counts by type, oldest/newest timestamps)

## Acceptance Criteria
1. `get_run_events` filters by session/type/timestamp/error and enforces strict limits.
2. `web_eval_agent` supports `mode` argument and sensible defaults based on URL host.
3. In `dev` mode, response includes bounded console/network excerpts; in `compact` it does not.
4. Tests cover filtering, limits, and mode default selection.

