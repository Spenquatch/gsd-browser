# Setup Guide

## Requirements
- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended; Makefile falls back to stdlib venv)
- pipx (installer script will install if missing)
- Docker (optional)

## Local Development
```bash
git clone ~/gsd/gsd-browser
cd gsd-browser/gsd-browser
curl -LsSf https://astral.sh/uv/install.sh | sh   # install uv if needed
make dev          # creates .venv via uv (or stdlib fallback)
cp .env.example .env
vim .env          # set LLM provider + API keys, LOG_LEVEL, GSD_BROWSER_JSON_LOGS, etc.
./scripts/run-local.sh
```
`./scripts/run-local.sh` runs the MCP stdio server (`serve`) from a checkout without a global install.

## .env Loading
By default, `gsd-browser` loads a `.env` file from the current working directory (if present), and then reads the process environment (shell env vars take precedence).

If your MCP host starts the server from a different working directory (common), set:
- `GSD_BROWSER_ENV_FILE=/absolute/path/to/your/.env`

## LLM Provider Configuration
`gsd-browser` supports both cloud providers and a local OSS path via Ollama.

Core variables:
- `GSD_BROWSER_LLM_PROVIDER`: `anthropic` (default), `openai`, `chatbrowseruse`, `ollama`
- `GSD_BROWSER_MODEL`: provider-specific model name (defaults to `claude-haiku-4-5`, or `bu-latest` for `chatbrowseruse`)

Required variables by provider:
- `anthropic`: `ANTHROPIC_API_KEY`
- `openai`: `OPENAI_API_KEY`
- `chatbrowseruse`: `BROWSER_USE_API_KEY` (optional `BROWSER_USE_LLM_URL`)
- `ollama`: `OLLAMA_HOST` (defaults to `http://localhost:11434`)

Quick validation:
```bash
gsd-browser validate-llm
gsd-browser validate-llm --llm-provider ollama --llm-model llama3.2
```

## pipx Installation
```bash
cd gsd-browser/gsd-browser
./tools/install.sh        # installs CLI globally
gsd-browser serve        # runs stdio server
```

Upgrade/reinstall as needed:
```bash
./tools/upgrade.sh
./tools/uninstall.sh
```

## Docker
```bash
docker build -t gsd-browser:dev -f docker/Dockerfile .
docker run --rm -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY gsd-browser:dev
```

## MCP Configuration
```bash
gsd-browser mcp-config --format json   # or toml
# or use the helper script
./scripts/print-mcp-config.py --format toml
```
Copy the output into your Claude MCP settings file. The snippet is also stored at `config/mcp-config-example.json`.

Notes:
- The MCP server command is `gsd-browser serve` (the snippet includes `args: ["serve"]`).
- If `gsd-browser` isn’t on your PATH yet, run `source .venv/bin/activate` or use `uv run gsd-browser mcp-config --format json`.
- Restart Claude after editing `~/.claude.json` (or a project `.claude.json`).

## MCP Tools
After Claude is connected to `gsd-browser`, it can call:
- `web_eval_agent` (runs a Playwright navigation + captures screenshots)
- `get_screenshots` (retrieves recent screenshots; set `include_images=False` for metadata-only)
- `setup_browser_state` (interactive login + saves browser state)

## Browser Streaming
See `docs/STREAMING.md` for running the streaming server, the dashboard UI, and auth configuration.
