# MCP Template

Reusable scaffold for building Model Context Protocol servers with repeatable installers, diagnostics, and packaging. The structure follows `../MCP_TEMPLATE_BLUEPRINT.md` and task tracking lives in `../tasks.json`.

## Features
- **UV-first dev workflow** (Makefile uses `uv` for venv + installs, with venv fallback)
- **Python package + CLI** (`mcp-template`) powered by Typer
- **Config loader** with `.env` + env var precedence and MCP snippet helper
- **Structured logging** with `--log-level`, `--json-logs/--text-logs`, and `LOG_LEVEL` / `MCP_TEMPLATE_JSON_LOGS`
- **Developer scripts** (`run-local`, `diagnose`, `smoke-test`, `check-mcp-config`, `print-mcp-config`)
- **pipx installers** for system-wide installation (`tools/install.sh`, `upgrade.sh`, `uninstall.sh`)
- **Docker image** with entrypoint + compose example
- **Smoke tests & Makefile** for lint/test/smoke/docker workflows

## Quick Start
```bash
git clone ~/gsd/mcp-template
cd mcp-template
curl -LsSf https://astral.sh/uv/install.sh | sh   # install uv once if not present
make dev        # sets up .venv (uv-backed)
./scripts/run-local.sh
```

## pipx Installation
```bash
./tools/install.sh
# later
./tools/upgrade.sh
./tools/uninstall.sh
```

## MCP Config Snippet
```bash
mcp-template mcp-config --format toml   # or json
```
or use the helper script:
```bash
./scripts/print-mcp-config.py --format json
```
Paste the output into your Claude MCP settings.

## Docker
```bash
docker build -t mcp-template:dev -f docker/Dockerfile .
docker run --rm -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY mcp-template:dev
```

## Docs
- `docs/SETUP.md` – local + pipx + Docker instructions
- `docs/TROUBLESHOOTING.md` – diagnostics workflow
- `docs/UPDATING.md` – rotating models/API keys + reinstalling
- `TEMPLATE_GUIDE.md` – adapting this scaffold for new MCP servers

See `../MCP_TEMPLATE_BLUEPRINT.md` for the exhaustive blueprint and `../tasks.json` for incremental upgrades.
