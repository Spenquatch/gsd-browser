# Updating Guide

## CLI Migration (`gsd` is canonical)
The canonical CLI is now `gsd`. The legacy `gsd-browser` executable remains available as a compatibility alias during a deprecation window (at least one minor release), but it prints a warning to stderr on each invocation:

```
Deprecated: use 'gsd …'
```

### Common command mappings
- `gsd-browser serve` → `gsd mcp serve`
- `gsd-browser mcp-config` → `gsd mcp config`
- `gsd-browser mcp-config-add <codex|claude>` → `gsd mcp add <codex|claude>`
- `gsd-browser mcp-tool-smoke ...` → `gsd mcp smoke ...`
- `gsd-browser list-tools` → `gsd mcp tools list`
- `gsd-browser mcp-tools ...` → `gsd mcp tools ...`
- `gsd-browser init-env` → `gsd config init`
- `gsd-browser configure` → `gsd config set`
- `gsd-browser ensure-browser ...` → `gsd browser ensure ...`
- `gsd-browser serve-browser ...` → `gsd stream serve ...`
- `gsd-browser validate-llm ...` → `gsd llm validate ...`
- `gsd-browser diagnose` → `gsd dev diagnose`
- `gsd-browser serve-echo ...` → `gsd dev echo ...`
- `gsd-browser smoke` → `gsd dev smoke`

### Update MCP host configs
MCP host configs must launch `gsd mcp serve`:
- `command="gsd"`
- `args=["mcp","serve"]`

You can generate an up-to-date snippet with:
```bash
gsd mcp config --format json   # or toml
```

## Model Changes
1. Edit `.env` or export a new `GSD_MODEL`.
2. Optionally update default in `src/gsd_browser/config.py`.
3. Restart the server (`gsd mcp serve`, legacy alias: `gsd-browser serve`).

## API Key Rotation
```bash
export ANTHROPIC_API_KEY=sk-ant-new-key
./scripts/run-local.sh        # or restart pipx/Docker instance
```
For persistent shells, edit `~/.bashrc`/`~/.zshrc` and reload.

## CLI Upgrade
```bash
cd gsd-browser/gsd-browser
git pull
./tools/upgrade.sh
```
This reinstalls via pipx and refreshes `~/.config/gsd/install.json`.

## Logging Adjustments
```bash
export LOG_LEVEL=DEBUG
export GSD_JSON_LOGS=true
gsd mcp serve --json-logs
```
Use CLI flags (`--log-level`, `--json-logs`, `--text-logs`) or env vars to tweak logging without editing code.

## Docker Rebuild
```bash
docker build -t gsd:dev -f docker/Dockerfile .
docker run --rm -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY gsd:dev
```

See `../GSD_BROWSER_BLUEPRINT.md` for additional context and best practices.
