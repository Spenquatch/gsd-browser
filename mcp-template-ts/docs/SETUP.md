# Setup Guide (TypeScript)

## Requirements
- Node.js 20+
- npm (or pnpm if preferred)
- Docker (optional for container workflow)

## Local Development
```bash
git clone ~/gsd/mcp-template-ts
cd mcp-template-ts
npm install
cp .env.example .env
# edit .env to set ANTHROPIC_API_KEY, LOG_LEVEL, MCP_TEMPLATE_JSON_LOGS, etc.
./scripts/run-local.sh
```

## npm Global Install
```bash
cd mcp-template-ts
./tools/install.sh
mcp-template-ts serve
```

Upgrade / uninstall:
```bash
./tools/upgrade.sh
./tools/uninstall.sh
```

## Docker
```bash
make docker-build
docker run --rm -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY mcp-template-ts:dev serve
```

## MCP Configuration Snippet
```bash
mcp-template-ts mcp-config --format json   # or toml
```
Paste into your Claude MCP configuration (`~/.claude.json` or project `.claude.json`).
