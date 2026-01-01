# MCP Server Template Blueprint (gsd)

This document captures what the existing `/home/inboxgreen/web-agent` project does for MCP server setup, highlights low-effort robustness improvements, and provides a reusable template plan for a generic MCP server scaffold to live under `~/gsd`.

## 1. Current Scaffolding Highlights
- **Multiple launch paths**: `run.sh` (repo-local), `web_eval_agent_launcher.py` (portable), and a Poetry-driven entry (`poetry run python main.py`) make it runnable from anywhere.
- **System-wide install**: `install.sh` copies the repo into `~/.web-eval-agent`, installs dependencies with Poetry, installs Playwright browsers, then drops wrapper binaries in `~/.local/bin` so users can run `web-eval-agent` globally.
- **Uninstall support**: `uninstall.sh` deletes the install dir, wrapper binaries, and the Xvfb process that might be left running.
- **MCP helpers**: `mcp-config-example.json` and `web-eval-agent-mcp-config` give the JSON/TOML snippet needed to register the server with Claude.
- **Diagnostics**: `check_mcp_config.sh`, `diagnose.sh`, smoke tests, and docs (`README.md`, `SETUP.md`, `UPDATING.md`) provide manual troubleshooting instructions.

## 2. Gaps & Low-Hanging Improvements
- `install.sh`: copies the entire repo every run but lacks incremental upgrades (no version file, no rsync delete to remove old files, no `--update` workflow). It also attempts to install Poetry and `xvfb` universally without OS detection beyond apt/yum, and it never validates whether those installs succeeded.
- `install.sh`: only copies `.env`/`.gitignore` as dotfiles when `rsync` is unavailable, so other hidden directories (e.g., `.config`, `.mcp`) would silently drop; there is no checksum/lockfile verification after `poetry install`.
- Wrapper creation bakes the absolute path to the virtualenv at install time; if the venv moves or Python is upgraded the command breaks with no self-heal logic or `poetry env use`.
- The runtime `run.sh` always shells through Poetry, so every invocation pays Poetry start-up costs and any Poetry stdout can corrupt MCP stdio. The installed wrapper avoids this, but dev usage still carries the risk.
- Uninstall only removes files but leaves behind installed apt packages (xvfb) and PATH edits, so the local environment is left “dirty.”
- Configuration relies on an ambient `ANTHROPIC_API_KEY` with optional `.env`, but there is no `.env.example`, typed config class, or schema validation.
- There is no standard `pipx`/`python -m build` packaging story, so redistributing the MCP server requires cloning the repo or running the bespoke install script.
- There is no containerized path (contrast with `anthropics/claude-quickstarts` computer-use demo) for users who prefer Dockerized MCP servers.

## 3. Template Objectives
- Provide a **turnkey scaffold** that any MCP server project can copy into `~/gsd/mcp-template` (or equivalent) and customize minimal knobs.
- Support **three install modes** out of the box: local dev (Poetry/uv), user-wide CLI (pipx + lightweight installer), and containerized Docker image.
- Offer **idempotent upgrade/uninstall workflows** with versioning, health checks, and cleanup steps.
- Make **configuration explicit** via `.env.example`, validation schema (pydantic or dataclasses), and CLI flags.
- Encapsulate dependency/runtime detection (Python >=3.11, Node, browsers) behind helper scripts to keep install logic readable.
- Include **diagnostic commands** and smoke tests that can be run post-install automatically.

## 4. Proposed Template Layout
```
mcp-template/
├── README.md
├── TEMPLATE_GUIDE.md                # instructions on customizing the scaffold
├── pyproject.toml                   # src layout with entry points
├── poetry.lock / uv.lock (optional)
├── src/
│   └── mcp_template/
│       ├── __init__.py
│       ├── main.py                  # stdio MCP server entry
│       ├── cli.py                   # argparse / typer CLI
│       ├── config.py                # config schema + loaders
│       └── server/
├── scripts/
│   ├── run-local.sh
│   ├── check-mcp-config.sh
│   ├── diagnose.sh
│   └── smoke-test.sh
├── tools/
│   ├── install.sh                   # thin wrapper around pipx install
│   ├── uninstall.sh
│   └── upgrade.sh
├── docker/
│   ├── Dockerfile
│   └── entrypoint.sh
├── config/
│   └── mcp-config-example.json
├── Makefile (or taskfile)
├── .env.example
└── tests/
    └── smoke/
```

## 5. Setup & Distribution Workflow

### 5.1 Local Developer Flow
1. `uv venv` or `poetry install` (auto-detect whichever tool is present).
2. `make dev` runs `pre-commit install`, installs Playwright/browser deps if needed, and prints MCP config snippet.
3. `scripts/run-local.sh` loads `.env`, verifies API keys, then executes `python -m mcp_template.main` without Poetry noise.

### 5.2 User-Wide CLI (pipx-first)
1. `tools/install.sh`:
   - Ensures Python 3.11+, installs `pipx` if missing, optionally falls back to in-project venv.
   - Builds the package (`pipx install --force --suffix @<version> .`) so the CLI lives under `~/.local/bin/mcp-template`.
   - Detects optional assets (Playwright browsers, headless display) and runs post-install hooks.
   - Writes a manifest at `~/.config/mcp-template/install.json` containing version, install path, python path, and env info.
2. `tools/upgrade.sh` reuses the manifest to reinstall with the pinned git ref or tag, running smoke tests afterward.
3. `tools/uninstall.sh` removes pipx env, deletes manifest, tears down background services, and optionally reverses PATH edits.

### 5.3 Container Image
- Provide `docker/Dockerfile` that installs dependencies, copies project, exposes ports, and defines an entrypoint that launches `python -m mcp_template.main`.
- Supply `docker-compose.yml` (optional) for running alongside dashboards or other services.
- Reference `anthropics/claude-quickstarts` “computer-use-demo” pattern for port mapping and env handling.

### 5.4 MCP Config Helper
- `scripts/print-mcp-config.py` prints JSON/TOML + VS Code snippet.
- `make mcp-config` writes to stdout; optionally `scripts/update-mcp-config.sh` can patch `~/.claude.json` safely (with backups).

## 6. Configuration & Secrets
- `.env.example` documents required/optional vars (API keys, feature flags).
- `src/mcp_template/config.py` defines a `Settings` object (pydantic or dataclass) that loads in priority order: CLI args → env vars → `.env`.
- Config validation errors produce actionable messages (similar to `webEvalAgent/config.py` but generalized).
- Provide `config/schema.json` for editors, and `scripts/validate-config.py` for CI.

## 7. CLI & Process Lifecycle
- Entry point `mcp-template` created via `project.scripts` entry in `pyproject.toml` (so no manual wrapper generation is required).
- CLI subcommands:
  - `serve` (default): runs stdio MCP server; supports flags `--model`, `--port` (for HTTP fallback), `--config`.
  - `diagnose`: runs dependency checks, verifies env vars, optionally runs a quick MCP handshake test.
  - `smoke-test`: executes automated scenario (e.g., call `scripts/smoke-test.sh`).
- Graceful shutdown: handle SIGINT/SIGTERM, close open child processes (playwright, browsers).
- Logging: default to structured logs on stderr with log level env var; `--json-logs` for automation.

## 8. Observability & Diagnostics
- `scripts/diagnose.sh` collects system info (python version, PATH, display status, playwright install) and prints actionable remediation steps.
- Optional `scripts/collect-support-bundle.sh` zips logs, config manifest, and diagnostics for support requests.
- Include `docs/troubleshooting.md` referencing the scripts and typical fixes (model updates, API key rotation, etc.).

## 9. Testing & Validation
- `tests/smoke/test_std_io.py` ensures the server responds to a minimal MCP handshake.
- `scripts/smoke-test.sh` is runnable post-install (CLI or pipx) to prove dependencies (Playwright, Xvfb) are healthy.
- GitHub Actions workflow (optional) runs lint, unit tests, and `pipx install . && mcp-template diagnose`.

## 10. Implementation Checklist (gsd)
1. Scaffold directories/files above inside `~/gsd/mcp-template`.
2. Wire `pyproject.toml` for `src/` layout, add entry point `mcp-template = mcp_template.cli:main`.
3. Port reusable bits from `web-agent`:
   - Virtual display bootstrap (but behind a feature flag).
   - Dashboard streaming toggle (if relevant).
   - Diagnostic scripts.
4. Implement `tools/install.sh`/`uninstall.sh` using pipx manifests instead of manual rsync copies.
5. Add `docker/Dockerfile` referencing `anthropics/claude-quickstarts` packaging approach for container users.
6. Create `.env.example`, `config/mcp-config-example.json`, and templates for docs (README, SETUP, TROUBLESHOOTING).
7. Write `scripts/check-mcp-config.sh` to inspect global + project Claude config (similar to existing script but templated).
8. Populate `Makefile` with targets: `dev`, `lint`, `serve`, `smoke`, `release`.
9. Document upgrade path in `docs/UPDATING.md` (model swaps, API key rotation, CLI reinstall).

Following this blueprint yields a robust, reusable MCP server template with first-class install/uninstall flows, clear configuration, and diagnostics that improve upon the current `web-agent` scaffolding.
