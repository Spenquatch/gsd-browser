# Updating Guide (TypeScript)

## Model / Config Changes
1. Update `.env` or export new values for `GSD_BROWSER_MODEL`, `LOG_LEVEL`, `GSD_BROWSER_JSON_LOGS`.
2. Restart the server (`gsd-browser-ts serve`).

## API Key Rotation
```bash
export ANTHROPIC_API_KEY=sk-ant-new
./scripts/run-local.sh
```
For persistent shells, edit `~/.bashrc`/`~/.zshrc`.

## CLI Upgrade
```bash
cd gsd-browser/gsd-browser-ts
git pull
./tools/upgrade.sh
```
Reinstalls via `npm install -g` and refreshes `~/.config/gsd-browser-ts/install.json`.

## Docker Rebuild
```bash
make docker-build
docker run --rm -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY gsd-browser-ts:dev serve
```

## Logging Overrides
```bash
gsd-browser-ts serve --log-level debug --json-logs
```
Override defaults temporarily while debugging.
