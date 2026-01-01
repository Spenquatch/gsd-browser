# Troubleshooting

## Quick Diagnostics
```bash
./scripts/diagnose.sh
```
This script prints:
- Python/tool versions (`uv`, `poetry`, `pipx`, `mcp-template`)
- Exposed environment variables
- Configuration validation (using `mcp_template.config`)
- MCP config snippet
- A smoke round-trip using `mcp-template serve --once`

## Common Issues
- **Missing API key**: Ensure `ANTHROPIC_API_KEY` exists in `.env` or shell. Diagnose output will show `(none set)`.
- **pipx command not found**: Rerun `./tools/install.sh` which bootstraps pipx via `python3 -m pip install --user pipx` and instructs you to add `~/.local/bin` to PATH.
- **Claude config entry not present**: Use `./scripts/check-mcp-config.sh` to inspect `~/.claude.json` and project `.claude.json`.
- **Log format surprises**: Export `LOG_LEVEL=DEBUG` or `MCP_TEMPLATE_JSON_LOGS=true` (or pass `--log-level DEBUG`, `--json-logs`, `--text-logs`) to control output.
- **Docker runtime errors**: Verify `docker/entrypoint.sh` has execute permissions (`chmod +x`) and that `ANTHROPIC_API_KEY` is passed via `docker run -e`.

If diagnosing remote environments, run `./scripts/collect-support-bundle.sh` once implemented (future work).
