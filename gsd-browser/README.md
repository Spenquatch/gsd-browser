# gsd (Python)

GSD MCP server (Python). The broader project docs live in `../GSD_BROWSER_BLUEPRINT.md` and task tracking lives in `../tasks.json`.

## Features
- **UV-first dev workflow** (Makefile uses `uv` for venv + installs, with venv fallback)
- **Python package + CLI** (`gsd`) powered by Typer
- **Config loader** with `.env` + env var precedence and MCP snippet helper
- **browser-use LLM provider selection** (Anthropic, OpenAI, ChatBrowserUse, Ollama)
- **Structured logging** with `--log-level`, `--json-logs/--text-logs`, and `LOG_LEVEL` / `GSD_JSON_LOGS`
- **Developer scripts** (`run-local`, `diagnose`, `smoke-test`, `check-mcp-config`, `print-mcp-config`)
- **pipx installers** for system-wide installation (`tools/install.sh`, `upgrade.sh`, `uninstall.sh`)
- **Docker image** with entrypoint + compose example
- **Smoke tests & Makefile** for lint/test/smoke/docker workflows

## Quick Start
```bash
git clone ~/gsd/gsd-browser
cd gsd-browser/gsd-browser
curl -LsSf https://astral.sh/uv/install.sh | sh   # install uv once if not present
make dev        # sets up .venv (uv-backed)
./scripts/run-local.sh
```

## .env Loading
`gsd` loads `.env` from the current working directory (if present) and then reads shell env vars (shell wins).

For production installs, prefer a stable user env file and point the server at it:
- Default user config: `~/.config/gsd/.env`
- Override path: `GSD_ENV_FILE=/absolute/path/to/.env`

Create/update the default user config with `gsd config init` and `gsd config set`.

## LLM Providers (browser-use)
`gsd` can run browser-use against either a cloud LLM (default: Anthropic) or a local OSS LLM (Ollama).

Provider selection:
- `GSD_LLM_PROVIDER`: `anthropic` (default), `openai`, `chatbrowseruse`, `ollama`
- `GSD_MODEL`: provider-specific model name (defaults to `claude-haiku-4-5`, or `bu-latest` for `chatbrowseruse`)

Required env vars:
- `anthropic`: `ANTHROPIC_API_KEY`
- `openai`: `OPENAI_API_KEY`
- `chatbrowseruse`: `BROWSER_USE_API_KEY` (optional `BROWSER_USE_LLM_URL`)
- `ollama`: `OLLAMA_HOST` (defaults to `http://localhost:11434`)

CLI overrides (useful for quick testing):
```bash
gsd llm validate --llm-provider ollama --llm-model llama3.2
gsd mcp serve --llm-provider ollama --llm-model llama3.2
```

## Browser Streaming
The template includes a Socket.IO + FastAPI streaming server for browser frames and a `/healthz` endpoint.

```bash
# Serve Socket.IO at /stream and /healthz on the same port
STREAMING_MODE=cdp STREAMING_QUALITY=med gsd stream serve --host 127.0.0.1 --port 5009
curl -sS http://127.0.0.1:5009/healthz
```

Environment toggles:
- `STREAMING_MODE`: `cdp` or `screenshot` (default: `cdp`)
- `STREAMING_QUALITY`: `low`, `med`, or `high` (default: `med`)

## pipx Installation
```bash
./tools/install.sh
# later
./tools/upgrade.sh
./tools/uninstall.sh
```

## MCP Config Snippet
```bash
gsd mcp config --format toml   # or json
```
or use the helper script:
```bash
./scripts/print-mcp-config.py --format json
```
Paste the output into your MCP host settings (Codex or Claude Code).

Notes:
- The MCP server is started via `gsd mcp serve` (the generated snippet includes `args: ["mcp", "serve"]`).
- If you're running from a checkout and `gsd` isn't on your PATH, run `source .venv/bin/activate` or use `uv run gsd mcp config --format json`.
- After updating `~/.claude.json` (or a project `.claude.json`), restart Claude so it picks up the new MCP server entry.
- To sanity-check your config file, run `./scripts/check-mcp-config.sh`.

## MCP Tools
Once configured as an MCP server, Claude can call:
- `web_eval_agent(url, task, headless_browser=False)` – runs a short Playwright evaluation and records screenshots.
- `setup_browser_state(url=None)` – opens a non-headless browser so you can log in, then saves state to `~/.operative/browser_state/state.json`.
- `get_screenshots(last_n=5, screenshot_type="agent_step", session_id=None, from_timestamp=None, has_error=None, include_images=True)` – retrieves recent screenshots (max `last_n=20`); set `include_images=False` for metadata-only.

For a quick end-to-end check:
```bash
gsd mcp smoke --skip-browser-task
```

## Docker
```bash
docker build -t gsd:dev -f docker/Dockerfile .
docker run --rm -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY gsd:dev
```

## Docs
- `docs/SETUP.md` – local + pipx + Docker instructions
- `docs/TROUBLESHOOTING.md` – diagnostics workflow
- `docs/UPDATING.md` – rotating models/API keys + reinstalling
- `TEMPLATE_GUIDE.md` – adapting this scaffold for new MCP servers

See `../GSD_BROWSER_BLUEPRINT.md` for the broader blueprint and `../tasks.json` for incremental upgrades.
