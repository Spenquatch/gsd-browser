# ADR-0006: MCP tool exposure controls (env + config + CLI)

## Status
Proposed

## Context
`gsd-browser` currently advertises a fixed set of MCP tools (e.g. `web_eval_agent`, `setup_browser_state`) to any MCP client that connects.

Operationally, we want a production-friendly way to:
- disable high-impact tools (e.g. those that open browsers or access local state) for certain environments
- ship a single server binary that can be safely used across different threat models and user preferences
- keep the MCP client UX clean by only advertising tools that are intended to be used in that deployment

## Decision
We will support tool exposure controls via environment variables and a small CLI surface that edits the user `.env` file.

### Configuration
Add two env/config levers:
- `GSD_BROWSER_MCP_ENABLED_TOOLS` (allowlist)
  - If set (non-empty), only these tools are advertised.
  - Special values: `all` / `*` (baseline = all tools), `none` (baseline = no tools).
- `GSD_BROWSER_MCP_DISABLED_TOOLS` (denylist)
  - If set, these tools are removed from the advertised set.

Effective advertised set:
1. baseline = all tools, unless `GSD_BROWSER_MCP_ENABLED_TOOLS` is set to a non-empty selector (including `none`)
2. advertised = baseline - `GSD_BROWSER_MCP_DISABLED_TOOLS`

Unknown tool names are ignored but logged as warnings.

### Implementation
At server startup, before `mcp.run(...)`, compute the advertised tool set and remove non-advertised tools from the `FastMCP` instance via `remove_tool`.

This approach ensures:
- MCP clients see an accurate `list_tools` response (disabled tools are not advertised)
- clients do not attempt to call tools that are meant to be disabled
- behavior remains consistent throughout the session (tool list is stable)

### CLI UX
Add CLI commands to view and manage tool exposure policy:
- `gsd-browser list-tools` (alias for `gsd-browser mcp-tools list`)
- `gsd-browser mcp-tools enable <tool...>`
- `gsd-browser mcp-tools disable <tool...>`
- `gsd-browser mcp-tools set-enabled [--all|--none|--clear] [tool...]`
- `gsd-browser mcp-tools set-disabled [--clear] [tool...]`
- `gsd-browser mcp-tools reset`

These commands update the user config file at:
- `$GSD_BROWSER_ENV_FILE` if set
- otherwise `~/.config/gsd-browser/.env`

Shell environment variables still override `.env` values.

## Consequences
### Positive
- Safer defaults in shared/locked-down environments without needing multiple binaries.
- Clearer MCP client UX: the client only sees tools that are intended to be used.
- Easier ops: admins can gate “power tools” without editing code.

### Tradeoffs / Risks
- Tool exposure is decided at process start; changes require restarting the MCP server session.
- The list of “known tools” must be kept in sync with tool definitions as new tools are added.

## Implementation Notes
- Prefer hiding tools by not advertising them (remove/unregister) rather than advertising-and-erroring.
- Keep the policy logic pure and unit-tested (parse + compute) with a small apply layer (`remove_tool`).
- Provide a minimal test that applies a policy to a `FastMCP` instance and asserts `list_tools` output.

## Open Questions
- Do we want a `GSD_BROWSER_MCP_TOOLSET=<preset>` layer (e.g. `safe`, `default`, `dev`) on top of allow/deny lists?
- Should unknown tool names be a hard error when set via CLI, while remaining warnings when set via env?

## References
- `docs/adr/README.md`
- `gsd-browser/src/gsd_browser/mcp_server.py`
- `gsd-browser/src/gsd_browser/mcp_tool_policy.py`

