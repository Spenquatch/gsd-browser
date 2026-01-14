# ADR-0007: CLI contract cleanup + rename `gsd-browser` to `gsd`

## Status
Proposed

## Context
The current CLI surface of `gsd-browser` has grown organically. It mixes:
- end-user ops commands (configure, ensure browser, MCP config)
- server commands (stdio MCP server, streaming server)
- developer/debug commands (echo server, smoke checks)
- partially overlapping MCP-tool related commands (`list-tools` vs `mcp-tools list`)

This creates discoverability and consistency issues:
- too many top-level commands for first-time users
- naming inconsistencies (hyphenated vs grouped nouns/verbs)
- unclear “areas” of responsibility (MCP vs streaming vs browser installation vs diagnostics)

We also want a shorter, nicer executable name: `gsd` instead of `gsd-browser`.

## Decision
Adopt a new CLI command tree rooted at `gsd` with noun-based groupings and consistent verb subcommands.

### 1) Binary name
- Primary executable: `gsd`
- Legacy alias: `gsd-browser` remains available for a deprecation window and forwards to `gsd`

### 2) Top-level groups (new command tree)
`gsd` will expose only a small set of top-level groups; most functionality moves under these groups:

- `gsd mcp …` (MCP server + MCP integration config + MCP tool exposure policy)
- `gsd browser …` (local browser/bootstrap + state management)
- `gsd stream …` (dashboard + streaming server)
- `gsd llm …` (provider validation and related tooling)
- `gsd config …` (user `.env` lifecycle; stable config file management)
- `gsd dev …` (developer-only and debugging utilities)

This reduces top-level command count and makes discovery via `--help` predictable.

### 3) CLI contract (commands, subcommands, and semantics)

#### `gsd --help`
Shows the above groups plus global options (at minimum `--version`).

#### `gsd mcp --help`
Commands:
- `gsd mcp serve` — start stdio MCP server (replaces `gsd-browser serve`)
- `gsd mcp config` — print MCP host config snippet (replaces `mcp-config`)
- `gsd mcp add` — add MCP config to a host (`codex`/`claude`) (replaces `mcp-config-add`)
- `gsd mcp tools …` — manage advertised tool list (replaces both `list-tools` and `mcp-tools …`)
- `gsd mcp smoke` — run MCP smoke checks (replaces `mcp-tool-smoke`)

Key semantics:
- `gsd mcp serve` must not write to stdout (stdio transport); all logs go to stderr.
- `gsd mcp tools …` edits the stable user config file (see `gsd config …`).
- Tool exposure changes take effect only when the MCP server process is restarted; the CLI should always print a restart hint after mutations.

#### `gsd mcp tools --help`
Commands (canonical names; no separate top-level alias like `list-tools`):
- `gsd mcp tools list` — print known tool names + effective advertised set
- `gsd mcp tools enable <tool...>` — remove tools from denylist; if allowlist is `none`, convert to allowlist of the enabled tools
- `gsd mcp tools disable <tool...>` — add tools to denylist; also removes from allowlist if present
- `gsd mcp tools allow <tool...>` — set allowlist exactly to these tools (alias: `set-enabled`)
- `gsd mcp tools deny <tool...>` — set denylist exactly to these tools (alias: `set-disabled`)
- `gsd mcp tools allow --all|--none|--clear` — set allowlist mode explicitly
- `gsd mcp tools deny --clear` — clear denylist
- `gsd mcp tools reset` — clear both allowlist and denylist

Environment variables (contract):
- `GSD_BROWSER_MCP_ENABLED_TOOLS`: allowlist selector (`all`/`*`, `none`, or comma-list)
- `GSD_BROWSER_MCP_DISABLED_TOOLS`: denylist comma-list

#### `gsd config --help`
Commands:
- `gsd config init` — create the stable per-user `.env` file if missing (replaces `init-env`)
- `gsd config set` — interactive/non-interactive setting of API keys (replaces `configure`)
- `gsd config path` — print the effective config path (new; helps automation)

Behavior:
- The “stable config” is `$GSD_BROWSER_ENV_FILE` if set, else `~/.config/gsd-browser/.env`.
- All commands that mutate config should state which file was updated.

#### `gsd browser --help`
Commands:
- `gsd browser ensure` — ensure a local Chromium/Chrome exists (replaces `ensure-browser`)
- `gsd browser state setup` — interactive browser state login (maps to current MCP tool behavior; optionally also exposed as CLI)
- `gsd browser state path` — print browser state path (new; for ops scripts)

#### `gsd stream --help`
Commands:
- `gsd stream serve` — start streaming server + dashboard (replaces `serve-browser`)
- `gsd stream smoke` — streaming smoke check (maps to current `smoke` if applicable)

#### `gsd llm --help`
Commands:
- `gsd llm validate` — validate provider configuration (replaces `validate-llm`)

#### `gsd dev --help`
Commands (explicitly labeled “debug/dev”, potentially hidden from normal docs):
- `gsd dev diagnose` — lightweight environment diagnostics (replaces `diagnose`)
- `gsd dev echo` — echo server (replaces `serve-echo`)
- `gsd dev smoke` — minimal runtime smoke (replaces `smoke`)

### 4) Help pages requirement (explicit contract)
Every group and command must have:
- a 1-line help summary visible in the parent’s `--help` output
- a longer help description explaining purpose and key environment variables
- at least one example invocation (shown in help text)

Minimum required help entry points:
- `gsd --help`
- `gsd mcp --help`
- `gsd mcp tools --help`
- `gsd config --help`
- `gsd browser --help`
- `gsd stream --help`
- `gsd llm --help`
- `gsd dev --help`

## Consequences
### Positive
- Cleaner discovery: the user can find everything under predictable groups.
- Better separation of concerns: MCP vs streaming vs browser/bootstrap vs diagnostics.
- Shorter command name improves everyday usage and copy/paste friendliness.
- Easier to document: one “CLI tree” section stays stable as features grow.

### Tradeoffs / Risks
- Breaking changes for existing scripts and MCP host configs if we remove old entry points too early.
- Requires a careful deprecation window and compatibility shims.
- MCP hosts may have different expectations around `command` + `args`; config generation must be tested across Codex/Claude.

## Implementation Notes
- Keep `gsd-browser` as an alias script that forwards to the new `gsd` app for at least one minor release.
- Maintain command-level backwards compatibility via aliases (e.g. `gsd-browser serve` continues to work, but prints a deprecation warning pointing to `gsd mcp serve`).
- Update `mcp-config` output to use `command="gsd"` and `args=["mcp","serve"]` once `gsd` exists.
- Keep stdout clean for `gsd mcp serve` (stdio MCP); log only to stderr.
- Ensure help pages include examples and call out restart requirement for tool exposure changes.

## Open Questions
- Should `gsd config set` be renamed to `gsd config configure` for familiarity, or is `set` preferred?
- Do we want `gsd mcp tools allow|deny` as the canonical verbs, or keep `set-enabled|set-disabled`?
- Should we adopt a “preset toolset” layer (e.g. `gsd mcp tools preset safe`)?
- Should `gsd dev …` be hidden from default docs, or still listed in `gsd --help`?

## References
- Current CLI: `gsd-browser/src/gsd_browser/cli.py`
- ADR format: `docs/adr/README.md`
- Tool exposure ADR: `docs/adr/ADR-0006-mcp-tool-exposure-controls.md`

