# Setup Guide

## Requirements
- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended; Makefile falls back to stdlib venv)
- pipx (installer script will install if missing)
- Docker (optional)

## Quickstart (pipx)
If you just want the CLI (recommended for non-dev usage):
```bash
pipx install gsd
gsd --version

gsd config init
gsd config set --anthropic-api-key sk-ant-...

gsd browser ensure --write-config
gsd mcp config --format json
```

## Windows (native)
The `tools/*.sh` and `scripts/*.sh` helpers are bash scripts (Linux/macOS). On Windows, install via pipx and use the `gsd` CLI directly:

```powershell
cd gsd-browser\gsd-browser

python -m pip install --user pipx
pipx ensurepath
# restart your shell
pipx install gsd

gsd config init
gsd config set --anthropic-api-key sk-ant-...
gsd browser ensure --write-config
gsd mcp config --format json
```

Alternatively, use the PowerShell helpers:
```powershell
cd gsd-browser\gsd-browser
.\tools\install.ps1
.\scripts\diagnose.ps1

# later:
.\tools\upgrade.ps1
.\tools\uninstall.ps1 -PurgeConfig
```

## Local Development
```bash
git clone ~/gsd/gsd-browser
cd gsd-browser/gsd-browser
curl -LsSf https://astral.sh/uv/install.sh | sh   # install uv if needed
make dev          # creates .venv via uv (or stdlib fallback)
cp .env.example .env
vim .env          # set LLM provider + API keys, LOG_LEVEL, GSD_JSON_LOGS, etc.
./scripts/run-local.sh
```
`./scripts/run-local.sh` runs the MCP stdio server (`serve`) from a checkout without a global install.

## .env Loading
By default, `gsd` loads a `.env` file from the current working directory (if present), and then reads the process environment (shell env vars take precedence).

If your MCP host starts the server from a different working directory (common), set:
- `GSD_ENV_FILE=/absolute/path/to/your/.env`

## LLM Provider Configuration
`gsd` supports both cloud providers and a local OSS path via Ollama.

Core variables:
- `GSD_LLM_PROVIDER`: `anthropic` (default), `openai`, `chatbrowseruse`, `ollama`
- `GSD_MODEL`: provider-specific model name (defaults to `claude-haiku-4-5`, or `bu-latest` for `chatbrowseruse`)

Required variables by provider:
- `anthropic`: `ANTHROPIC_API_KEY`
- `openai`: `OPENAI_API_KEY`
- `chatbrowseruse`: `BROWSER_USE_API_KEY` (optional `BROWSER_USE_LLM_URL`)
- `ollama`: `OLLAMA_HOST` (defaults to `http://localhost:11434`)

Quick validation:
```bash
gsd llm validate
gsd llm validate --llm-provider ollama --llm-model llama3.2
```

## pipx Installation
```bash
cd gsd-browser/gsd-browser
./tools/install.sh        # installs CLI globally
gsd mcp serve            # runs stdio server (legacy alias: `gsd-browser serve`)
```

Upgrade/reinstall as needed:
```bash
./tools/upgrade.sh
./tools/uninstall.sh
# (optional) remove user config too
./tools/uninstall.sh --purge-config
```

## Docker
```bash
docker build -t gsd:dev -f docker/Dockerfile .
docker run --rm -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY gsd:dev
```

## MCP Configuration
```bash
gsd mcp config --format json   # or toml
# or use the helper script
uv run ./scripts/print-mcp-config.py --format toml
```
Copy the output into your MCP host config (Codex or Claude Code).

By default, the snippet points at `~/.gsd/.env` via `GSD_ENV_FILE` so it works regardless of working directory.
Initialize/update that file with:
```bash
gsd config set
```

Notes:
- The MCP server command is `gsd mcp serve` (the snippet includes `args: ["mcp", "serve"]`).
- If `gsd` isn't on your PATH yet, run `source .venv/bin/activate` or use `uv run gsd mcp config --format json`.
- Restart Claude after editing `~/.claude.json` (or a project `.claude.json`).

## MCP Tools
After Claude is connected to `gsd`, it can call:
- `web_eval_agent` (runs a Playwright navigation + captures screenshots)
- `web_task_agent` (general-purpose web task runner; does not use saved auth state by default)
- `web_task_agent_github` (GitHub workflows using a dedicated `github` saved state)
- `get_screenshots` (retrieves recent screenshots; set `include_images=False` for metadata-only)
- `get_run_events` (fetches stored console/network/agent run events for a session)
- `setup_browser_state` (interactive login + saves browser state; supports `state_id` for multiple profiles)

### Browser state profiles (multiple saved sessions)
`setup_browser_state` supports a `state_id` so you can maintain separate authenticated sessions per tool/workflow.

Examples:
- Default state: `setup_browser_state(url="https://example.com/login")` → `~/.gsd/browser_state/state.json`
- Named state: `setup_browser_state(url="https://github.com/login", state_id="github")` → `~/.gsd/browser_state/states/github.json`

The `web_task_agent` tool does not use saved state by default. State-bound tools (example: `web_task_agent_github`) load only their configured `state_id`.

You can also capture state from the CLI:
```bash
gsd browser state setup --url "https://github.com/login" --state-id github
```

To manually verify a saved state loads (and that you’re signed in), open a browser with it:
```bash
gsd browser state open --url "https://chatgpt.com" --state-id gpt-pro
```

If a site flags Playwright-managed Chromium as automated, try using your system Chrome:
```bash
gsd browser state setup --url "https://chatgpt.com" --state-id gpt-pro --browser-channel chrome
```

To add your own state-bound tool/workflow:
1. Add a new `@mcp.tool` wrapper in `gsd-browser/src/gsd_browser/mcp_server.py` that sets a fixed `state_id` override and calls `web_eval_agent`.
2. Add the tool name to `gsd-browser/src/gsd_browser/mcp_tool_policy.py` so it shows up in `gsd mcp tools list` and can be enabled/disabled.

### Tool exposure controls (enable/disable tools)
You can restrict which tools are advertised to MCP clients via:
- `GSD_MCP_ENABLED_TOOLS` (allowlist; supports `all`/`*` and `none`)
- `GSD_MCP_DISABLED_TOOLS` (denylist)

Convenience commands (edits `~/.gsd/.env` unless `GSD_ENV_FILE` is set):
```bash
gsd mcp tools list
gsd mcp tools disable setup_browser_state
gsd mcp tools allow web_eval_agent,get_run_events
gsd mcp tools reset
```

Restart your MCP host/session (Codex/Claude) after changing tool policy so it refreshes `list_tools`.

## Task Execution Timeouts

By default, `web_eval_agent` uses browser-use's built-in defaults for timeouts and step limits. You can override these via environment variables or MCP client parameters.

**Environment variables** (optional - leave unset to use browser-use defaults):
- `GSD_WEB_EVAL_BUDGET_S` – overall task timeout in seconds
- `GSD_WEB_EVAL_MAX_STEPS` – maximum number of agent steps
- `GSD_WEB_EVAL_STEP_TIMEOUT_S` – per-step timeout in seconds

**Priority order** (highest to lowest):
1. MCP client parameters (passed directly to `web_eval_agent`)
2. Environment variables (if set)
3. browser-use library defaults (if env vars unset)

Example: Set a 5-minute budget with max 50 steps:
```bash
GSD_WEB_EVAL_BUDGET_S=300
GSD_WEB_EVAL_MAX_STEPS=50
```

MCP clients can also pass `budget_s`, `max_steps`, and `step_timeout_s` parameters directly to override any defaults.

## Browser Streaming
See `docs/STREAMING.md` for running the streaming server, the dashboard UI, and auth configuration.
