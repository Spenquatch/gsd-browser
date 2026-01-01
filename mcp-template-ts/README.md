# MCP Template (TypeScript)

Reusable Model Context Protocol server template implemented in TypeScript. Mirrors the Python template but uses Node.js tooling (npm + TypeScript) while following `../MCP_TEMPLATE_BLUEPRINT.md` and `tasks.json`.

## Features
- **Node 20+/TypeScript** project with `commander` CLI (`mcp-template-ts`)
- **Config loader** via `dotenv` + `zod` with JSON/TOML MCP snippet helpers
- **Structured logging** powered by `pino` with `--log-level`, `--json-logs`, and `--text-logs` overrides
- **Developer scripts** (`scripts/run-local.sh`, `diagnose.sh`, `smoke-test.sh`, `check-mcp-config.sh`)
- **Global installer** (`tools/install.sh`, `upgrade.sh`, `uninstall.sh`) that uses `npm install -g`
- **Docker packaging** (Node slim image + entrypoint)
- **Vitest smoke test** and Makefile wrappers for lint/test/smoke/docker

## Quick Start
```bash
cd mcp-template-ts
npm install         # or pnpm install
./scripts/run-local.sh --once
```

### Development Scripts
```bash
npm run dev        # tsx CLI with hot reload
npm run lint       # eslint
npm run test       # vitest
make smoke         # build + tests + CLI round trip
```

## Global Installation
```bash
./tools/install.sh
mcp-template-ts serve --log-level debug
# Upgrades / removal
./tools/upgrade.sh
./tools/uninstall.sh
```

## MCP Configuration Snippet
```bash
mcp-template-ts mcp-config --format toml   # or json
```
Add the snippet to your Claude MCP settings (`~/.claude.json` or project `.claude.json`). Use `scripts/check-mcp-config.sh` to verify entries.

## Docker
```bash
make docker-build
ANOTHER_VAR=1 docker run --rm \
  -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
  mcp-template-ts:dev serve --json-logs
```

## Logging Controls
- Env vars: `LOG_LEVEL`, `MCP_TEMPLATE_JSON_LOGS`
- CLI flags: `--log-level`, `--json-logs`, `--text-logs`

## Documentation
- `docs/SETUP.md` – install/run instructions (local, npm global, Docker)
- `docs/TROUBLESHOOTING.md` – diagnostics workflow & common fixes
- `docs/UPDATING.md` – model/API rotation, npm upgrade, logging overrides
- `TEMPLATE_GUIDE.md` – checklist for adapting this scaffold to another MCP server

See `tasks.json` for outstanding work if you keep extending the template.
