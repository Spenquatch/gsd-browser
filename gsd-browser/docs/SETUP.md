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
vim .env          # set ANTHROPIC_API_KEY, LOG_LEVEL, GSD_BROWSER_JSON_LOGS, etc.
./scripts/run-local.sh
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
