# Template Guide

This guide summarizes how to adapt the scaffold for a new MCP server. The full reasoning lives in `../GSD_BROWSER_BLUEPRINT.md`; use this file as a quick checklist.

1. **Clone + rename**: Copy the entire directory, update `pyproject.toml` (`name`, `description`, entry points) and the `src/gsd_browser` namespace. Run `make dev` (which uses `uv` when available) so dependencies install inside `.venv` without touching system pip.
2. **Implement server logic**: Replace `gsd_browser.main` with your actual MCP stdio implementation and extend CLI commands as needed.
3. **Adjust configuration**: Update `config.py` defaults + `.env.example` to match your service requirements. Ensure `scripts/print-mcp-config.py` and `gsd-browser mcp-config` emit the correct snippet.
4. **Customize scripts**: `scripts/run-local.sh`, `diagnose.sh`, `smoke-test.sh`, and `check-mcp-config.sh` can be tuned for dependencies (Playwright, GPU, etc.).
5. **Installer tweaks**: Update `tools/install.sh` manifest metadata or extra dependency steps (e.g., Playwright browser install, apt packages).
6. **Docker image**: Modify `docker/Dockerfile` and `docker/compose.yml` to expose relevant ports/services.
7. **Docs**: Keep `docs/SETUP.md`, `TROUBLESHOOTING.md`, and `UPDATING.md` current with the changes above.

Track incremental work in `../tasks.json` when extending the template further.
