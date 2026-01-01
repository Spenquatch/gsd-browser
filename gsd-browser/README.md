# gsd-browser (Python)

GSD Browser MCP server (Python). The broader project docs live in `../GSD_BROWSER_BLUEPRINT.md` and task tracking lives in `../tasks.json`.

## Features
- **UV-first dev workflow** (Makefile uses `uv` for venv + installs, with venv fallback)
- **Python package + CLI** (`gsd-browser`) powered by Typer
- **Config loader** with `.env` + env var precedence and MCP snippet helper
- **Structured logging** with `--log-level`, `--json-logs/--text-logs`, and `LOG_LEVEL` / `GSD_BROWSER_JSON_LOGS`
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

## Browser Streaming
The template includes a Socket.IO + FastAPI streaming server for browser frames and a `/healthz` endpoint.

```bash
# Serve Socket.IO at /stream and /healthz on the same port
STREAMING_MODE=cdp STREAMING_QUALITY=med gsd-browser serve-browser --host 127.0.0.1 --port 5009
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
gsd-browser mcp-config --format toml   # or json
```
or use the helper script:
```bash
./scripts/print-mcp-config.py --format json
```
Paste the output into your Claude MCP settings.

## Docker
```bash
docker build -t gsd-browser:dev -f docker/Dockerfile .
docker run --rm -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY gsd-browser:dev
```

## Docs
- `docs/SETUP.md` – local + pipx + Docker instructions
- `docs/TROUBLESHOOTING.md` – diagnostics workflow
- `docs/UPDATING.md` – rotating models/API keys + reinstalling
- `TEMPLATE_GUIDE.md` – adapting this scaffold for new MCP servers

See `../GSD_BROWSER_BLUEPRINT.md` for the broader blueprint and `../tasks.json` for incremental upgrades.
