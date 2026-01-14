# AI Entrypoint (Read This First)

This repository uses a task-driven workflow. When you start a new implementation session, follow the steps below exactly.

## Source of Truth

- Task list: `tasks.json`
- CLI contract decision record: `docs/adr/ADR-0007-cli-contract-and-gsd-binary.md`

`tasks.json` defines the implementation requirements and acceptance criteria. Do not make assumptions that contradict it. If you find a missing requirement, update `tasks.json` first (in its own commit), then continue.

## Workflow (Per Session)

1. **Read** `docs/adr/ADR-0007-cli-contract-and-gsd-binary.md` and `tasks.json`.
2. **Pick the next unfinished task** in `tasks.json` by `id` order (CLI-001, CLI-002, …).
3. **Log your work** in `session_log.md`:
   - Add a “Start” entry for the task with timestamp and brief plan.
4. **Implement only that task** (keep the change set focused).
5. **Run validation** appropriate to the change:
   - Prefer targeted tests first (new/affected unit tests).
   - If you change packaging/CLI wiring, also run CLI help tests.
   - If you can, run `cd gsd-browser && make lint` and `cd gsd-browser && make test`.
6. **Commit** the change.
7. **Log completion** in `session_log.md`:
   - Add a “Finish” entry for the task with timestamp, what changed, commands run, and the commit SHA.

Repeat until all tasks are complete.

## Commit Requirements

- Commit after finishing each task.
- Use the repo’s prefix convention seen in history:
  - `feat: ...`, `fix: ...`, `docs: ...`, `test: ...`
- Keep commits scoped to one task ID.
- Suggested subject format: `<prefix>: <short summary> (CLI-00X)`

## Logging Requirements (session_log.md)

For every task you touch in a session, log:

- Task ID (e.g. `CLI-004`)
- Start timestamp (ISO-8601, local time okay)
- Finish timestamp
- What changed (1–4 bullets)
- Validation commands run + results
- Commit SHA(s)
- Any known follow-ups or blockers

Do not include secrets (API keys) in logs.

## Guardrails / Non-Negotiables

- **Do not break stdio MCP:** `gsd mcp serve` (and the legacy shim that routes to it) must not write non-JSON-RPC content to stdout. Deprecation warnings must go to stderr.
- **No secrets:** Never commit API keys or private tokens. Avoid printing them to logs.
- **Respect stable config location:** Use `$GSD_BROWSER_ENV_FILE` if set; otherwise `~/.config/gsd-browser/.env`.
- **Avoid touching `wt/`:** do not add/modify committed files under `wt/`.

## Implementation Order (Recommended)

Follow task IDs in order:

1. `CLI-001` — Packaging entrypoints (`gsd` + legacy `gsd-browser`)
2. `CLI-002` — Canonical `gsd` command tree skeleton + help scaffolding
3. `CLI-003` — `gsd mcp` group (`serve`, `config`, `add`, `smoke`, `tools`)
4. `CLI-004` — `gsd mcp tools` contract (parsing + output format)
5. `CLI-005` — `gsd config` group
6. `CLI-006` — `gsd browser` / `gsd stream` / `gsd llm` groups
7. `CLI-007` — `gsd dev` group
8. `CLI-008` — Legacy shims + deprecation mapping
9. `CLI-009` — Docs + installer scripts updated to `gsd`
10. `CLI-010` — Help page coverage check
11. `CLI-011` — Automated tests for the CLI contract
12. `CLI-012` — Finalize ADR + migration notes

## Quick Reference Commands

- Lint: `cd gsd-browser && make lint`
- Tests: `cd gsd-browser && make test`
- Print MCP config: `gsd mcp config --format toml` (after CLI migration is implemented)

