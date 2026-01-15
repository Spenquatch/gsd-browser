# B3 – MCP Tooling & Screenshot Services Spec

## Scope
- Define MCP tools mirroring web-agent:
  - `web_eval_agent`: run evaluation via template CLI (launch browser task, logging, tool_call_id).
  - `setup_browser_state`: interactive auth/browser state saver.
  - `get_screenshots`: expose filters (`last_n`, `screenshot_type`, `session_id`, `from_timestamp`, `has_error`, `include_images`).
- Integrate screenshot manager stats with MCP response context and docs.
- Port CLI diagnostics scripts (`diagnose.sh`, `smoke-test.sh`, `scripts/mcp_tool_smoke.py`) to the template with uv/poetry awareness.
- Provide tests covering screenshot filters + MCP tool envelopes (use stubs/mocks).

## Acceptance Criteria
1. MCP server registers the three tools with docstrings matching Claude usage; `get_screenshots` enforces `last_n ≤ 20`.
2. Screenshot filters (session, type, timestamp, error flag, metadata-only) behave as in `web-agent`, verified via pytest.
3. Diagnostic scripts run against the template’s CLI/env and surface streaming stats.
4. README/docs include usage instructions for MCP snippet + screenshot tool.
5. No logging/system-level secrets leak through MCP payloads (structured logging sanitized).

## Out of Scope
- Dashboard UI or streaming security (B2).
- Browser-use dependency upgrades or OSS LLM plumbing (B4).
