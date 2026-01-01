# Setup Guide

## Requirements
- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended; Makefile falls back to stdlib venv)
- pipx (installer script will install if missing)
- Docker (optional)

## Local Development
```bash
git clone ~/gsd/mcp-template
cd mcp-template
curl -LsSf https://astral.sh/uv/install.sh | sh   # install uv if needed
make dev          # creates .venv via uv (or stdlib fallback)
cp .env.example .env
vim .env          # set ANTHROPIC_API_KEY, LOG_LEVEL, MCP_TEMPLATE_JSON_LOGS, etc.
./scripts/run-local.sh
```

## pipx Installation
```bash
cd mcp-template
./tools/install.sh        # installs CLI globally
mcp-template serve        # runs stdio server
```

Upgrade/reinstall as needed:
```bash
./tools/upgrade.sh
./tools/uninstall.sh
```

## Docker
```bash
docker build -t mcp-template:dev -f docker/Dockerfile .
docker run --rm -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY mcp-template:dev
```

## MCP Configuration
```bash
mcp-template mcp-config --format json   # or toml
# or use the helper script
./scripts/print-mcp-config.py --format toml
```
Copy the output into your Claude MCP settings file. The snippet is also stored at `config/mcp-config-example.json`.
