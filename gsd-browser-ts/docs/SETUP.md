# Setup Guide (TypeScript)

## Requirements
- Node.js 20+
- npm (or pnpm if preferred)
- Docker (optional for container workflow)

## Local Development
```bash
git clone ~/gsd/gsd-browser
cd gsd-browser/gsd-browser-ts
npm install
cp .env.example .env
# edit .env to set ANTHROPIC_API_KEY, LOG_LEVEL, GSD_BROWSER_JSON_LOGS, etc.
./scripts/run-local.sh
```

## npm Global Install
```bash
cd gsd-browser/gsd-browser-ts
./tools/install.sh
gsd-browser-ts serve
```

Upgrade / uninstall:
```bash
./tools/upgrade.sh
./tools/uninstall.sh
```

## Docker
```bash
make docker-build
docker run --rm -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY gsd-browser-ts:dev serve
```

## MCP Configuration Snippet
```bash
gsd-browser-ts mcp-config --format json   # or toml
```
Paste into your Claude MCP configuration (`~/.claude.json` or project `.claude.json`).
