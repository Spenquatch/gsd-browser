# A4 — Harness actionable classification for agent failures

## Scope
Make the real-world sanity harness treat “agent/provider/schema validation” failures as actionable so expected failure scenarios classify as `soft_fail` when artifacts exist.

### Requirements
- Update the harness “actionable reason” predicate so that:
  - agent/provider/schema failure summaries (from tool payload and/or run events) count as actionable, even without console/network errors
  - judge failure_reason remains actionable (when present)
- Keep the classification rules stable:
  - `pass`: `status=success` and non-empty `result`
  - `soft_fail`: `status=failed|partial` + artifacts + actionable reason
  - `hard_fail`: missing artifacts OR no actionable reason

## Acceptance criteria
1. Fixture tests cover:
   - schema validation failure + artifacts → `soft_fail`
   - provider error + artifacts → `soft_fail`
   - failed + no artifacts → `hard_fail`
2. Real-world harness expected-soft-fail scenarios classify as `soft_fail` (not `hard_fail`) when artifacts are present.

## Out of scope
- Recording new run event types (A3 owns persistence).
- Prompt wrapper content changes (A1).
- Screenshot capture timing changes (A2).

