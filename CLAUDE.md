# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is **gsd-browser**, an MCP (Model Context Protocol) server template that enables AI agents to control web browsers for automated task execution. The project includes both Python and TypeScript implementations and follows a task-driven development workflow.

## Repository Structure

- `gsd-browser/`: Python MCP server (primary implementation)
  - Source: `gsd-browser/src/gsd_browser/`
  - Tests: `gsd-browser/tests/`
  - Docs: `gsd-browser/docs/`
- `gsd-browser-ts/`: TypeScript MCP server template
  - Source: `gsd-browser-ts/src/`
  - Output: `gsd-browser-ts/dist/`
- `docs/`: Project-wide documentation including ADRs
- `tasks.json`: Implementation task tracking
- `wt/`: Git worktrees (do not commit contents)

## Development Commands

### Python (gsd-browser/)

From repository root:
```bash
make py-dev         # Create .venv (prefers uv) and install editable deps
make py-lint        # Run Ruff lint
make py-test        # Run pytest
make py-smoke       # Run smoke test script
make py-diagnose    # Run diagnostics
```

From `gsd-browser/` directory:
```bash
make dev            # Setup environment
make lint           # Ruff check
make test           # Pytest
make smoke          # Smoke test
```

### TypeScript (gsd-browser-ts/)

From repository root:
```bash
make ts-install     # Install npm dependencies
make ts-dev         # Run dev server
make ts-lint        # ESLint
make ts-test        # Vitest
make ts-smoke       # Smoke test
```

From `gsd-browser-ts/` directory:
```bash
npm install         # Install dependencies
npm run build       # Compile TypeScript
npm run dev         # Dev mode with tsx
npm test            # Run Vitest
npm run lint        # ESLint
```

## CLI Architecture

The project is migrating from `gsd-browser` to a new `gsd` command structure (see `docs/adr/ADR-0007-cli-contract-and-gsd-binary.md`).

### Current CLI Structure (gsd)

```
gsd/
├── mcp/              # MCP server operations
│   ├── serve         # Start MCP stdio server
│   ├── config        # Output MCP config snippet (JSON/TOML)
│   ├── add           # Integrate with Claude/Codex
│   ├── smoke         # Test MCP tools
│   └── tools/        # Manage tool exposure
│       ├── list, enable, disable, allow, deny
├── config/           # Environment file management
│   ├── init, set, path
├── browser/          # Browser installation & management
│   ├── ensure, state
├── stream/           # Dashboard & streaming server
│   ├── serve, smoke
├── llm/              # LLM provider validation
│   └── validate
└── dev/              # Diagnostics & debug tools
    ├── diagnose, echo, smoke
```

### Entry Points

- `gsd_cli.py`: Canonical modern CLI (Typer-based)
- `legacy_cli.py`: Backward compatibility shim for `gsd-browser` command
- `cli.py`: Historical CLI implementation

## Core Architecture

### Python Implementation

**Configuration Loading Chain** (highest to lowest priority):
1. Shell environment variables
2. `GSD_ENV_FILE` (if set)
3. `.env` (current directory)
4. `~/.gsd/.env` (production default)
5. Pydantic field defaults

**Key Modules**:
- `mcp_server.py`: FastMCP stdio server exposing 4 tools (web_eval_agent, get_screenshots, setup_browser_state, get_run_events)
- `config.py`: Pydantic-based Settings model with environment validation
- `runtime.py`: AppRuntime singleton managing dashboard and shared state
- `streaming/server.py`: FastAPI + Socket.IO for real-time browser updates
- `mcp_tool_policy.py`: Tool exposure controls via allowlist/denylist

**MCP Tools Exposed**:
1. `web_eval_agent`: Browser automation with task execution (uses browser-use framework)
2. `get_screenshots`: Retrieve captured screenshots with filtering
3. `setup_browser_state`: Interactive browser login/auth setup
4. `get_run_events`: Retrieve execution telemetry (agent steps, console, network)

**LLM Providers Supported**:
- Anthropic (default): `claude-haiku-4-5`, `claude-sonnet-4-5`
- OpenAI: `gpt-4o-mini`, etc.
- Browser Use API: `bu-latest`, `bu-1-0`
- Ollama: Local models like `llama3.2`

**Streaming Architecture**:
- Separate daemon thread runs FastAPI + Socket.IO server (default port 5009)
- CDP (Chrome DevTools Protocol) screencast for frame streaming
- Take-control feature for manual browser interaction via WebSocket
- Dashboard available at `http://localhost:5009/` when enabled

### TypeScript Implementation

**Modules**:
- `cli.ts`: Commander-based CLI with serve/diagnose/mcp-config commands
- `server.ts`: Stdio-based MCP server (currently template/echo implementation)
- `config.ts`: Zod schema validation for environment configuration
- `logging.ts`: Pino logger with JSON/pretty modes

**Configuration**: Pydantic validates `ANTHROPIC_API_KEY` (required), `GSD_MODEL`, `LOG_LEVEL`, `GSD_JSON_LOGS`

## Configuration Management

### Environment Variables

**LLM Provider**:
- `GSD_LLM_PROVIDER`: `anthropic` | `openai` | `chatbrowseruse` | `ollama`
- `GSD_MODEL`: Provider-specific model name
- `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `BROWSER_USE_API_KEY`, `OLLAMA_HOST`

**Browser & Execution**:
- `GSD_WEB_EVAL_BUDGET_S`: Task timeout (240s default)
- `GSD_WEB_EVAL_MAX_STEPS`: Max agent iterations (25 default)
- `GSD_WEB_EVAL_STEP_TIMEOUT_S`: Per-step timeout (15s default)
- `GSD_USE_VISION`: `auto` | `true` | `false`

**Streaming**:
- `STREAMING_MODE`: `cdp` | `screenshot`
- `STREAMING_QUALITY`: `low` | `med` | `high`

**MCP Tool Controls**:
- `GSD_MCP_ENABLED_TOOLS`: Allowlist (comma-separated or `all`/`none`)
- `GSD_MCP_DISABLED_TOOLS`: Denylist (comma-separated)

### Configuration Files

- `.env.example`: Template for environment variables (both Python and TypeScript)
- `~/.gsd/.env`: Production user config (managed by `gsd config` commands)
- `config/mcp-config-example.json`: Example MCP host configuration

## Task-Driven Workflow

The project follows a strict task-driven workflow documented in `AI_ENTRYPOINT.md`:

1. **Source of Truth**: `tasks.json` and `docs/adr/ADR-0007-cli-contract-and-gsd-binary.md`
2. **Per Session**:
   - Read `tasks.json` and pick next unfinished task by ID order
   - Log start in `session_log.md` with timestamp and plan
   - Implement only that task
   - Run validation (targeted tests, lint, smoke tests)
   - Commit with prefix convention (`feat:`, `fix:`, `docs:`, `test:`)
   - Log completion in `session_log.md` with changes, commands, and commit SHA

3. **Commit Format**: `<prefix>: <summary> (CLI-00X)`
4. **Logging Format**: ISO-8601 timestamps, bullet points, no secrets

### Non-Negotiables

- **Do not break stdio MCP**: `gsd mcp serve` must not write non-JSON-RPC to stdout
- **No secrets**: Never commit API keys or tokens
- **Respect stable config location**: Use `$GSD_ENV_FILE` or `~/.gsd/.env`
- **Avoid touching `wt/`**: Do not add/modify committed files under `wt/`

## Testing

### Python Tests

- Unit tests: `gsd-browser/tests/` using pytest
- Smoke tests: `./scripts/smoke-test.sh`
- Real-world sanity: `SANITY_REAL_CONFIRM=1 make py-sanity-real`
- MCP tool smoke: `gsd mcp smoke`

### TypeScript Tests

- Unit tests: Vitest in `gsd-browser-ts/tests/`
- Smoke test: `npm run smoke` (build + single message round-trip)

## Key Design Patterns

### Tool Exposure Policy

Tools are dynamically advertised based on environment variables:
```python
Allowlist (ENABLED_TOOLS) → enabled tools
Denylist (DISABLED_TOOLS) → removed from advertised set
Advertised = enabled - disabled
```

Managed via `gsd mcp tools` commands (enable/disable/allow/deny).

### Lazy Dashboard Initialization

Dashboard server only starts on first `web_eval_agent` call to reduce startup time for CLI-only usage.

### Streaming in Separate Thread

Uvicorn runs in daemon thread with shared event loop to avoid blocking MCP stdio message loop.

### Configuration Priority

Shell env vars override .env files, which override defaults. Multiple .env locations support dev/production scenarios.

## Important Files for Understanding

**Python** (priority order):
1. `gsd-browser/src/gsd_browser/mcp_server.py` - Core MCP tool implementations
2. `gsd-browser/src/gsd_browser/config.py` - Configuration management
3. `gsd-browser/src/gsd_browser/gsd_cli.py` - User-facing CLI
4. `gsd-browser/src/gsd_browser/runtime.py` - State management
5. `gsd-browser/src/gsd_browser/streaming/server.py` - Real-time streaming

**TypeScript**:
1. `gsd-browser-ts/src/cli.ts` - CLI structure
2. `gsd-browser-ts/src/server.ts` - MCP server loop
3. `gsd-browser-ts/src/config.ts` - Configuration schema

**Project Documentation**:
1. `AI_ENTRYPOINT.md` - Session workflow (read first)
2. `docs/adr/ADR-0007-cli-contract-and-gsd-binary.md` - CLI architecture decisions
3. `GSD_BROWSER_BLUEPRINT.md` - Template design philosophy
4. `tasks.json` - Implementation task list

## Common Workflows

### Adding a New MCP Tool

1. Add tool function to `gsd-browser/src/gsd_browser/mcp_server.py`
2. Add tool name to `KNOWN_MCP_TOOLS` in `mcp_tool_policy.py`
3. Update tests in `gsd-browser/tests/`
4. Update documentation

### Changing Configuration

1. Update `Settings` class in `config.py` (Python) or schema in `config.ts` (TypeScript)
2. Update `.env.example`
3. Update `to_mcp_snippet()` / `to_mcp_toml()` if MCP-relevant
4. Update docs/UPDATING.md if user-facing

### Modifying CLI Commands

1. Edit `gsd_cli.py` for new command structure
2. Update `legacy_cli.py` if old commands affected
3. Ensure help text includes examples
4. Update ADR-0007 if contract changes
5. Test with both `gsd` and `gsd-browser` (legacy)

## Installation & Distribution

### Development Setup

```bash
# Python
cd gsd-browser
make dev

# TypeScript
cd gsd-browser-ts
npm install
```

### System-Wide Installation (Python)

```bash
cd gsd-browser
./tools/install.sh     # pipx-based install
./tools/upgrade.sh     # Upgrade existing install
./tools/uninstall.sh   # Remove install
```

### Docker

```bash
cd gsd-browser
make docker-build
make docker-run
```

## Troubleshooting

- **Diagnostics**: Run `gsd dev diagnose` or `make py-diagnose`
- **Check MCP config**: `./scripts/check-mcp-config.sh`
- **Validate LLM setup**: `gsd llm validate`
- **Smoke test**: `gsd mcp smoke` or `make py-smoke`
- **Logs**: Check stderr output; use `--log-level debug` for verbose output

## Additional Resources

- `gsd-browser/docs/SETUP.md` - Installation instructions
- `gsd-browser/docs/TROUBLESHOOTING.md` - Diagnostic workflows
- `gsd-browser/docs/UPDATING.md` - Configuration updates
- `gsd-browser/docs/STREAMING.md` - Streaming architecture details
- `gsd-browser/TEMPLATE_GUIDE.md` - Adapting scaffold for new MCP servers
- `gsd-browser-ts/TEMPLATE_GUIDE.md` - TypeScript template customization
