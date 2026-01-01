# Updating Guide

## Model Changes
1. Edit `.env` or export a new `MCP_TEMPLATE_MODEL`.
2. Optionally update default in `src/mcp_template/config.py`.
3. Restart the server (`mcp-template serve`).

## API Key Rotation
```bash
export ANTHROPIC_API_KEY=sk-ant-new-key
./scripts/run-local.sh        # or restart pipx/Docker instance
```
For persistent shells, edit `~/.bashrc`/`~/.zshrc` and reload.

## CLI Upgrade
```bash
cd mcp-template
git pull
./tools/upgrade.sh
```
This reinstalls via pipx and refreshes `~/.config/mcp-template/install.json`.

## Logging Adjustments
```bash
export LOG_LEVEL=DEBUG
export MCP_TEMPLATE_JSON_LOGS=true
mcp-template serve --json-logs
```
Use CLI flags (`--log-level`, `--json-logs`, `--text-logs`) or env vars to tweak logging without editing code.

## Docker Rebuild
```bash
docker build -t mcp-template:dev -f docker/Dockerfile .
docker run --rm -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY mcp-template:dev
```

See `../MCP_TEMPLATE_BLUEPRINT.md` for additional context and best practices when evolving the template.
