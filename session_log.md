# Session Log

This file is append-only. Add entries at the bottom.

## Template

### <YYYY-MM-DD> — <short session name>

**Task:** `CLI-00X` — <task title>

**Start:** <ISO-8601 timestamp>

**Plan:**
- <1–4 bullets>

**Finish:** <ISO-8601 timestamp>

**Changes:**
- <1–6 bullets>

**Validation:**
- `<command>` → <pass/fail + brief note>

**Commits:**
- `<sha>` `<subject>`

**Notes / Follow-ups:**
- <optional>

---

## Entries

### 2026-01-14 — CLI migration kickoff

**Task:** `CLI-001` — Add new `gsd` console script (keep `gsd-browser` as legacy alias)

**Start:** 2026-01-14T19:13:43+00:00

**Plan:**
- Add `gsd` + `gsd-browser` console scripts
- Implement `gsd mcp serve` and a legacy deprecation shim
- Validate CLI help/version and stdio stdout constraints
- Run `make lint` and `make test`

**Finish:** 2026-01-14T19:21:05+00:00

**Changes:**
- Added canonical `gsd` Typer app (`gsd mcp serve`) and kept version output consistent
- Added `gsd-browser` legacy shim that forwards to the old CLI and prints deprecation warnings to stderr
- Updated packaging to expose both console scripts (`gsd` and `gsd-browser`)

**Validation:**
- `cd gsd-browser && make dev` → pass
- `cd gsd-browser && .venv/bin/ruff check src/gsd_browser/gsd_cli.py src/gsd_browser/legacy_cli.py` → pass
- `cd gsd-browser && make lint` → fail (pre-existing Ruff violations in `scripts/` and `src/gsd_browser/real_world_sanity.py`)
- `cd gsd-browser && make test` → fail (pre-existing `tests/test_real_world_sanity_r4.py::test_r4_default_scenarios_match_plan_ids`)

**Commits:**
- `f2bfadd` `feat: add gsd entrypoint (CLI-001)`

---

### 2026-01-14 — Repo hygiene: restore green lint/test

**Task:** `MAINT-001` — Fix pre-existing lint/test failures

**Start:** 2026-01-14T19:23:00+00:00

**Plan:**
- Fix Ruff failures in scripts and sanity harness
- Align `DEFAULT_SCENARIOS` with the test contract
- Re-run `make lint` and `make test`

**Finish:** 2026-01-14T19:40:48+00:00

**Changes:**
- Reflowed long lines and removed an unused import in `gsd-browser/scripts/prompt_comparison_harness.py`
- Updated `DEFAULT_SCENARIOS` in `gsd-browser/src/gsd_browser/real_world_sanity.py` to match the test contract

**Validation:**
- `cd gsd-browser && make lint` → pass
- `cd gsd-browser && make test` → pass

**Commits:**
- `0d20c7d` `fix: restore green lint/test (MAINT-001)`

---

### 2026-01-14 — Canonical CLI skeleton

**Task:** `CLI-002` — Create canonical `gsd` command tree skeleton (groups + help)

**Start:** 2026-01-14T19:47:46+00:00

**Plan:**
- Add missing top-level groups to `gsd` (`config`, `browser`, `stream`, `llm`, `dev`)
- Ensure each group help includes `Examples:`
- Validate `--help` entry points + run lint/tests

**Finish:** 2026-01-14T19:49:45+00:00

**Changes:**
- Added canonical `gsd` top-level groups: `mcp`, `config`, `browser`, `stream`, `llm`, `dev`
- Ensured each group help page contains `Examples:`

**Validation:**
- `gsd --help` → pass (lists only the six groups)
- `gsd mcp/config/browser/stream/llm/dev --help` → pass (each contains `Examples:`)
- `cd gsd-browser && make lint` → pass
- `cd gsd-browser && make test` → pass

**Commits:**
- `0f2da0b` `feat: add gsd command tree skeleton (CLI-002)`

---

### 2026-01-14 — MCP group migration

**Task:** `CLI-003` — Implement `gsd mcp` group: serve/config/add/smoke/tools

**Start:** 2026-01-14T19:52:44+00:00

**Plan:**
- Move MCP config printing to `gsd mcp config` (command=`gsd`, args=`mcp serve`)
- Implement `gsd mcp add` and `gsd mcp smoke` option parity
- Ensure `gsd mcp --help` lists `serve`, `config`, `add`, `smoke`, `tools`

**Finish:** 2026-01-14T19:55:15+00:00

**Changes:**
- Updated MCP config snippet generation to use `command="gsd"` and `args=["mcp","serve"]`
- Added `gsd mcp config`, `gsd mcp add`, and `gsd mcp smoke` (with option parity)
- Ensured `gsd mcp add` writes nothing to stdout

**Validation:**
- `cd gsd-browser && make lint` → pass
- `cd gsd-browser && make test` → pass

**Commits:**
- `538cd0f` `feat: implement gsd mcp group (CLI-003)`

---

### 2026-01-14 — MCP tools contract + legacy shims

**Task:** `CLI-004` — Implement `gsd mcp tools` group: list/enable/disable/allow/deny/reset

**Start:** 2026-01-14T19:55:55+00:00

**Plan:**
- Implement tool parsing + mutation output contract for `gsd mcp tools`
- Route legacy `list-tools` / `mcp-tools ...` commands through canonical code path
- Run lint/tests and commit

**Finish:** 2026-01-14T20:01:03+00:00

**Changes:**
- Implemented `gsd mcp tools` with deterministic parsing and mutation output contract
- Added legacy shims so `gsd-browser list-tools` / `gsd-browser mcp-tools ...` execute the canonical code path

**Validation:**
- `cd gsd-browser && make lint` → pass
- `cd gsd-browser && make test` → pass

**Commits:**
- `086d439` `feat: implement gsd mcp tools contract (CLI-004)`

---

### 2026-01-14 — Config group migration

**Task:** `CLI-005` — Implement `gsd config` group: init/set/path

**Start:** 2026-01-14T20:07:45+00:00

**Plan:**
- Implement `gsd config path/init/set` with path selection rules
- Ensure write commands print `Updated: <path>` and `config path` prints only the path
- Run lint/tests and commit

**Finish:** 2026-01-14T20:08:55+00:00

**Changes:**
- Added `gsd config path`, `gsd config init`, and `gsd config set` with deterministic path selection
- Ensured `gsd config path` prints only the resolved path and write commands emit `Updated: <path>`

**Validation:**
- `cd gsd-browser && make lint` → pass
- `cd gsd-browser && make test` → pass

**Commits:**
- `ce0d0cd` `feat: implement gsd config group (CLI-005)`

---

### 2026-01-14 — Browser/stream/LLM group migration

**Task:** `CLI-006` — Implement `gsd browser`, `gsd stream`, and `gsd llm` groups

**Start:** 2026-01-14T20:09:32+00:00

**Plan:**
- Implement `gsd browser ensure`, `gsd stream serve`, `gsd llm validate` with option parity
- Ensure `gsd browser ensure --write-config` emits `Updated: <path>`
- Run lint/tests and commit

**Finish:** 2026-01-14T20:11:37+00:00

**Changes:**
- Added `gsd browser ensure`, `gsd stream serve`, and `gsd llm validate` with option parity
- Ensured `gsd browser ensure --write-config` prints `Updated: <path>` on writes

**Validation:**
- `cd gsd-browser && make lint` → pass
- `cd gsd-browser && make test` → pass

**Commits:**
- `dda5837` `feat: implement browser/stream/llm groups (CLI-006)`

---

### 2026-01-14 — Dev group migration

**Task:** `CLI-007` — Implement `gsd dev` group: diagnose/echo/smoke

**Start:** 2026-01-14T20:12:20+00:00

**Plan:**
- Add `gsd dev diagnose`, `gsd dev echo`, `gsd dev smoke` with option parity
- Ensure `gsd dev echo --help` exposes `--no-echo` and `--once`
- Run lint/tests and commit

**Finish:** 2026-01-14T20:14:00+00:00

**Changes:**
- Added `gsd dev diagnose`, `gsd dev echo`, and `gsd dev smoke` (wrapping the existing implementations)

**Validation:**
- `cd gsd-browser && make lint` → pass
- `cd gsd-browser && make test` → pass

**Commits:**
- `77f70eb` `feat: implement gsd dev group (CLI-007)`

---

### 2026-01-14 — Legacy CLI shims mapping

**Task:** `CLI-008` — Backwards compatibility + deprecation mapping (old -> new)

**Start:** 2026-01-14T20:32:33+00:00

**Plan:**
- Ensure `gsd-browser` forwards all mapped legacy commands into the canonical `gsd` code path
- Preserve exit codes and stdout/stderr behavior (warning only on stderr)
- Run lint/tests and commit

**Finish:** 2026-01-14T20:34:23+00:00

**Changes:**
- Updated the legacy shim to forward all mapped legacy subcommands into the canonical `gsd` CLI
- Kept the single mapping dict as the source of truth and preserved stderr-only deprecation warnings

**Validation:**
- `cd gsd-browser && make lint` → pass
- `cd gsd-browser && make test` → pass

**Commits:**
- `df33e8b` `fix: forward gsd-browser shims to gsd (CLI-008)`

---

### 2026-01-14 — Docs + install scripts use `gsd`

**Task:** `CLI-009` — Update docs + installer scripts to use `gsd`

**Start:** 2026-01-14T20:36:34+00:00

**Plan:**
- Update docs to present `gsd` as canonical (keep `gsd-browser` as legacy alias)
- Update installer/upgrade/uninstall scripts to prefer `gsd` and fall back to `gsd-browser`
- Ensure any generated MCP config uses `command="gsd"` and `args=["mcp","serve"]`

**Finish:** 2026-01-14T20:42:11+00:00

**Changes:**
- Updated setup/troubleshooting/updating docs to use canonical `gsd ...` commands (keeping `gsd-browser` as a legacy alias)
- Updated install/upgrade scripts to run `gsd` when available and fall back to `gsd-browser`
- Updated the MCP config printer helper script to describe the new canonical command

**Validation:**
- `bash -n gsd-browser/tools/install.sh gsd-browser/tools/upgrade.sh gsd-browser/tools/uninstall.sh` → pass
- `cd gsd-browser && make lint` → pass
- `cd gsd-browser && make test` → pass

**Commits:**
- `2898947` `docs: update docs and scripts to gsd (CLI-009)`

---

### 2026-01-14 — Help pages coverage

**Task:** `CLI-010` — Help pages: ensure complete coverage and examples

**Start:** 2026-01-14T20:43:52+00:00

**Plan:**
- Ensure `gsd --help` includes `Examples:`
- Ensure `gsd mcp tools --help` explicitly mentions restarting the MCP host/session after changes
- Run lint/tests and commit

**Finish:** 2026-01-14T20:44:51+00:00

**Changes:**
- Added an `Examples:` epilog to `gsd --help`
- Added an explicit restart note to `gsd mcp tools --help` (tool exposure changes require restarting the MCP host/session)

**Validation:**
- `cd gsd-browser && for cmd in "" "mcp" "mcp tools" "config" "browser" "stream" "llm" "dev"; do .venv/bin/gsd $cmd --help | rg -q "Examples:"; done` → pass
- `cd gsd-browser && make lint` → pass
- `cd gsd-browser && make test` → pass

**Commits:**
- `9f025d1` `docs: improve gsd help pages (CLI-010)`
