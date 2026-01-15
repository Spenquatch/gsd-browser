# O1a – Orchestrated `web_eval_agent` (minimal) + JSON response contract

## Scope
- Replace the screenshot-only `web_eval_agent` behavior with a browser-use Agent run that:
  - Runs the agent against the provided `url` and `task`.
  - Extracts the final answer via `AgentHistoryList.final_result()` (browser-use ≥0.11).
  - Returns a single JSON `TextContent` payload (see contract) and never returns images.
- Create and return a `session_id` for artifact association (even though O1a stores minimal artifacts).
- Ensure MCP stdio safety: no stdout output once the server starts.

## Response Contract (MCP compliant, flexible, text-first)
`web_eval_agent` returns `list[TextContent]` with one item whose `text` is JSON:
- `version`: `"gsd-browser.web_eval_agent.v1"`
- `session_id`: string
- `tool_call_id`: string
- `url`: string (normalized)
- `task`: string
- `mode`: `"compact" | "dev"` (in O1a, may be `"compact"` only; O2b expands)
- `status`: `"success" | "failed" | "partial"`
- `result`: string | null (from `final_result()` if present)
- `summary`: string (bounded; ≤ ~2k chars)
- `artifacts`: object (counts; in O1a can be zeros)
- `next_actions`: array of suggested tool calls (strings)

## Acceptance Criteria
1. `web_eval_agent(url, task, ...)` runs browser-use and returns JSON with `session_id` and `status`.
2. If the agent provides a final answer, `result` is non-null and matches `final_result()`.
3. No images are returned inline.
4. No stdout logging breaks MCP stdio.
5. Unit tests can validate result extraction and JSON shape using mocked `AgentHistoryList`.

## Out of Scope
- Screenshot capture and pause gating (O1b).
- Run event store and `get_run_events` tool (O2a/O2b).
- Take-control input routing (O3*).

