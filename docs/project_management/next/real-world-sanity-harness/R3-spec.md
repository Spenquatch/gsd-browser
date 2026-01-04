# R3 – Report formatting (Markdown + summary JSON)

## Scope
### 1) summary.json schema
Write a stable `summary.json` at the run root with:
- timestamp (`started_at`)
- output directory
- env/provider hints (no secrets)
- per-scenario results:
  - expected outcome
  - tool status + classification
  - counts (screenshots, error events)
  - paths for the per-scenario bundle
  - “highlights” list (errors-first summaries; bounded)

### 2) Markdown report
Write `report.md` that is PR-friendly:
- short header with timestamp and output path
- one section per scenario containing:
  - URL, expected outcome, tool status, classification
  - artifact links (relative paths)
  - highlights (errors-first; bounded)

## Acceptance Criteria
1. The harness emits `report.md` and `summary.json` at the run root.
2. Report content is stable and compact enough to paste into PR description.
3. Unit tests validate Markdown rendering for a fixed fake summary payload.

## Out of Scope
- PR checklist/quality gates docs (R4).

