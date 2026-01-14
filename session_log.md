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
