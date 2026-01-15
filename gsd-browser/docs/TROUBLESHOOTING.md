# Troubleshooting

## Quick Diagnostics
```bash
./scripts/diagnose.sh
```
This script prints:
- Python/tool versions (`uv`, `poetry`, `pipx`, `gsd`)
- Exposed environment variables
- Configuration validation (using `gsd_browser.config`)
- MCP config snippet
- A smoke round-trip using `gsd dev echo --once`

## Common Issues
- **Missing API key**: Ensure the provider-specific variable is set (e.g. `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `BROWSER_USE_API_KEY`). Run `gsd llm validate` to confirm.
- **.env not being picked up**: The server loads `.env` from the current working directory by default, and also checks `~/.config/gsd/.env` when no local `.env` exists. If your MCP host launches the server elsewhere, set `GSD_ENV_FILE=/absolute/path/to/.env`.
- **No browser installed**: `browser-use` needs a local Chromium/Chrome executable. Run `gsd browser ensure` (this installs Playwright Chromium using the current Python environment).
- **Tool missing / not advertised**: Your MCP host only sees the tool list at session start. If you changed `GSD_MCP_ENABLED_TOOLS` / `GSD_MCP_DISABLED_TOOLS`, restart Codex/Claude (or otherwise restart the MCP session).
- **pipx command not found**: Rerun `./tools/install.sh` which bootstraps pipx via `python3 -m pip install --user pipx` and instructs you to add `~/.local/bin` to PATH.
- **Claude config entry not present**: Use `./scripts/check-mcp-config.sh` to inspect `~/.claude.json` and project `.claude.json`.
- **Claude MCP entry runs but exits immediately**: Ensure the config runs `gsd mcp serve` (i.e., `args: ["mcp", "serve"]` in the JSON snippet).
- **Log format surprises**: Export `LOG_LEVEL=DEBUG` or `GSD_JSON_LOGS=true` (or pass `--log-level DEBUG`, `--json-logs`, `--text-logs`) to control output.
- **Docker runtime errors**: Verify `docker/entrypoint.sh` has execute permissions (`chmod +x`) and that `ANTHROPIC_API_KEY` is passed via `docker run -e`.
- **Task timing out**: By default, browser-use's built-in timeouts are used. If tasks are timing out, you can increase limits via `GSD_WEB_EVAL_BUDGET_S` (overall timeout), `GSD_WEB_EVAL_MAX_STEPS` (step limit), or `GSD_WEB_EVAL_STEP_TIMEOUT_S` (per-step timeout). MCP clients can also pass these directly to `web_eval_agent`.

If MCP tools are behaving oddly, run:
```bash
gsd mcp smoke --skip-browser-task
```

If diagnosing remote environments, run `./scripts/collect-support-bundle.sh` once implemented (future work).
