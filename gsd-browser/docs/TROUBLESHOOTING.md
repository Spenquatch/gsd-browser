# Troubleshooting

## Quick Diagnostics
```bash
./scripts/diagnose.sh
```
This script prints:
- Python/tool versions (`uv`, `poetry`, `pipx`, `gsd-browser`)
- Exposed environment variables
- Configuration validation (using `gsd_browser.config`)
- MCP config snippet
- A smoke round-trip using `gsd-browser serve-echo --once`

## Common Issues
- **Missing API key**: Ensure the provider-specific variable is set (e.g. `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `BROWSER_USE_API_KEY`). Run `gsd-browser validate-llm` to confirm.
- **.env not being picked up**: The server loads `.env` from the current working directory by default. If your MCP host launches the server elsewhere, set `GSD_BROWSER_ENV_FILE=/absolute/path/to/.env`.
- **pipx command not found**: Rerun `./tools/install.sh` which bootstraps pipx via `python3 -m pip install --user pipx` and instructs you to add `~/.local/bin` to PATH.
- **Claude config entry not present**: Use `./scripts/check-mcp-config.sh` to inspect `~/.claude.json` and project `.claude.json`.
- **Claude MCP entry runs but exits immediately**: Ensure the config runs `gsd-browser serve` (i.e., `args: ["serve"]` in the JSON snippet).
- **Log format surprises**: Export `LOG_LEVEL=DEBUG` or `GSD_BROWSER_JSON_LOGS=true` (or pass `--log-level DEBUG`, `--json-logs`, `--text-logs`) to control output.
- **Docker runtime errors**: Verify `docker/entrypoint.sh` has execute permissions (`chmod +x`) and that `ANTHROPIC_API_KEY` is passed via `docker run -e`.

If MCP tools are behaving oddly, run:
```bash
gsd-browser mcp-tool-smoke --skip-browser-task
```

If diagnosing remote environments, run `./scripts/collect-support-bundle.sh` once implemented (future work).
