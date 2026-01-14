# Updating Guide

## Model Changes
1. Edit `.env` or export a new `GSD_BROWSER_MODEL`.
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
This reinstalls via pipx and refreshes `~/.config/gsd-browser/install.json`.

## Logging Adjustments
```bash
export LOG_LEVEL=DEBUG
export GSD_BROWSER_JSON_LOGS=true
gsd mcp serve --json-logs
```
Use CLI flags (`--log-level`, `--json-logs`, `--text-logs`) or env vars to tweak logging without editing code.

## Docker Rebuild
```bash
docker build -t gsd-browser:dev -f docker/Dockerfile .
docker run --rm -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY gsd-browser:dev
```

See `../GSD_BROWSER_BLUEPRINT.md` for additional context and best practices.
