# Updating Guide (TypeScript)

## Model / Config Changes
1. Update `.env` or export new values for `MCP_TEMPLATE_MODEL`, `LOG_LEVEL`, `MCP_TEMPLATE_JSON_LOGS`.
2. Restart the server (`mcp-template-ts serve`).

## API Key Rotation
```bash
export ANTHROPIC_API_KEY=sk-ant-new
./scripts/run-local.sh
```
For persistent shells, edit `~/.bashrc`/`~/.zshrc`.

## CLI Upgrade
```bash
cd mcp-template-ts
git pull
./tools/upgrade.sh
```
Reinstalls via `npm install -g` and refreshes `~/.config/mcp-template-ts/install.json`.

## Docker Rebuild
```bash
make docker-build
docker run --rm -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY mcp-template-ts:dev serve
```

## Logging Overrides
```bash
mcp-template-ts serve --log-level debug --json-logs
```
Override defaults temporarily while debugging.
