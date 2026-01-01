# Template Guide (TypeScript)

Use this checklist when adapting the TypeScript scaffold for another MCP server. See `../MCP_TEMPLATE_BLUEPRINT.md` for rationale.

1. **Clone & rename**: Copy the repo, update `package.json` (`name`, `bin`), and rename the namespaces under `src/`.
2. **Implement server logic**: Replace `serveStdio` with your MCP stdio implementation, extend CLI commands as needed.
3. **Configuration**: Adjust defaults in `src/config.ts`, `.env.example`, and ensure `mcp-config` outputs match your binary name.
4. **Logging**: Keep `pino` structured logging; customize transports/fields as needed.
5. **Scripts & installers**: Update `scripts/*.sh` or `tools/*.sh` if your server needs extra dependencies (Playwright, browsers, etc.).
6. **Docker**: Modify `docker/Dockerfile`/`compose.yml` when additional services or ports are required.
7. **Docs**: Refresh README + docs to document any new environment variables or steps.

Track incremental work in `tasks.json` to keep the template reproducible.
