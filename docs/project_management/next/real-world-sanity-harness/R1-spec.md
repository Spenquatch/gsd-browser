# R1 – Harness runner + scenario registry

## Scope
Implementation should extend the existing harness rather than rebuild it:
- Module entrypoint: `python -m gsd_browser.real_world_sanity`
- Script wrapper: `gsd-browser/scripts/real_world_sanity.py`

### 1) Script/CLI shape
Provide a harness entrypoint (script or CLI subcommand) that can:
- run one or more scenarios through `web_eval_agent`
- write the output bundle tree described in `plan.md`
- run scenarios sequentially by default; allow limited concurrency as an opt-in (bounded to avoid load/ToS risk)

### 2) Scenario registry
Define a small curated scenario set with stable ids and minimal expectations:
- Wikipedia content extraction (pass)
- Hacker News navigation + extraction (pass)
- GitHub UI navigation + anchor extraction (pass)
- Hugging Face bot-wall friction probe (soft_fail expected)

### 3) Runtime knobs
Support:
- selecting scenarios by id
- overriding headless mode (global)
- setting output directory

## Acceptance Criteria
1. Harness can run one or all scenarios and writes the expected directory structure.
2. Scenario ids are stable and documented in code.
3. Harness does not print secrets; it can print a minimal “configured?” hint.

## Out of Scope
- Artifact harvesting mechanics and classification rules (R2).
- Report formatting (R3).
- PR checklist/quality gates docs (R4).
