# Troubleshooting (TypeScript)

## Quick Diagnostics
Run the helper script:
```bash
./scripts/diagnose.sh
```
It prints Node/npm versions, checks `node_modules`, and runs `gsd-browser-ts diagnose`.

## Common Issues
- **Missing deps**: If `node_modules` is missing, run `npm install` (or `pnpm install`).
- **API key not set**: Ensure `.env` or your shell exports `ANTHROPIC_API_KEY`. `diagnose` will print `(undefined)` otherwise.
- **Logging format surprises**: Adjust `LOG_LEVEL` / `GSD_BROWSER_JSON_LOGS`, or use CLI flags `--log-level`, `--json-logs`, `--text-logs`.
- **Claude config entry missing**: Use `./scripts/check-mcp-config.sh` to inspect `~/.claude.json` and project `.claude.json`.
- **Docker issues**: Confirm `docker/entrypoint.sh` is executable and pass required env vars with `-e`.

Collect support data (future work): add a script to bundle logs + manifests if needed.
