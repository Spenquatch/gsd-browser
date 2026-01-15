# R2 – Artifact harvesting + classification

## Scope
### 1) Artifact harvesting (out-of-band)
After each scenario run:
- persist the tool response JSON (`response.json`)
- retrieve step screenshots (type `agent_step`) and write them to `screenshots/`
- retrieve run events (console/network/agent), filter for error events, and persist `events.json`
- persist a `screenshots.json` index (metadata without embedded bytes)

### 2) Classification rules
Implement stable classification:
- `pass`: tool `status=success` and `result` is non-empty
- `soft_fail`: tool `status=failed|partial` AND we have artifacts AND an actionable reason
- `hard_fail`: missing artifacts OR no actionable reason

Define “actionable reason” for the harness as a conservative predicate (bounded, deterministic):
- a console exception/error event, or
- a network 4xx/5xx event, or
- explicit failure_reason fields in the tool payload (if present)

## Acceptance Criteria
1. For every scenario, the harness produces `response.json`, `events.json`, `screenshots/`, and `screenshots.json`.
2. `hard_fail` only occurs when artifacts are missing or actionable reason is absent.
3. Unit tests can validate classification logic using fixed fixtures (no network).

## Out of Scope
- Markdown report formatting (R3).
- PR checklist/quality gates docs (R4).

