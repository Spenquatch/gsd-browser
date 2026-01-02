# Repository Guidelines

## Project Structure & Module Organization

- `gsd-browser/`: Python MCP server template (primary). Source: `gsd-browser/src/gsd_browser/`. Tests: `gsd-browser/tests/`. Docs: `gsd-browser/docs/`.
- `gsd-browser-ts/`: TypeScript MCP server template. Source: `gsd-browser-ts/src/`. Output: `gsd-browser-ts/dist/`. Tests via Vitest.
- `docs/`, `triads/`, `tasks.json`: project planning/orchestration artifacts.
- `wt/`: local git worktrees (created by developers/agents); do not commit contents under `wt/`.

## Build, Test, and Development Commands

Python (`gsd-browser/`):
- `make dev`: create `.venv` (prefers `uv`) and install editable deps.
- `make lint`: run `ruff check`.
- `make test`: run `pytest`.
- `make smoke`: run `./scripts/smoke-test.sh` (lightweight runtime smoke).
- Format/lint equivalents: `uv run ruff format --check` and `uv run ruff check`.

TypeScript (`gsd-browser-ts/`):
- `npm install`: install dependencies.
- `npm run build`: compile (`tsc`).
- `npm run dev`: run CLI in dev mode (`tsx src/cli.ts serve`).
- `npm test`: run `vitest run`.
- `npm run lint`: run ESLint; formatting via Prettier (`.prettierrc.json`).

## Coding Style & Naming Conventions

- Python: 4-space indentation; type hints expected; keep modules/functions `snake_case`, classes `CapWords`.
- Tooling: Ruff is the source of truth for formatting and lint rules (see `gsd-browser/pyproject.toml`).
- TypeScript: follow ESLint + Prettier; prefer explicit types at module boundaries.

## Testing Guidelines

- Python: Pytest tests live in `gsd-browser/tests/` and use `test_*.py` naming. Prefer small, fast unit tests; keep smoke tests deterministic.
- TypeScript: Vitest tests should run via `npm test`; keep fixtures local to `gsd-browser-ts/`.

## Commit & Pull Request Guidelines

- Commit messages follow a simple prefix convention seen in history: `feat:`, `fix:`, `test:`, `docs:` (keep subject line short and scoped).
- PRs should include: what changed, how to run it, and which commands you ran (e.g., `make test`, `npm test`). Add screenshots only for UI/dashboard changes.

## Security & Configuration Tips

- Never commit secrets. For Python config, copy `gsd-browser/.env.example` to `.env` and set provider-specific vars (e.g., `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `BROWSER_USE_API_KEY`, `OLLAMA_HOST`).
