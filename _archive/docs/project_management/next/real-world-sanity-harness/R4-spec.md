# R4 – Quality gates (manual PR checklist)

## Scope
Add a documented, opt-in quality gate for PRs that touch:
- `web_eval_agent` orchestration
- streaming / screenshots / run events
- take-control / pause semantics

Gate requirements:
- run the real-world sanity harness locally
- attach the report directory (or paste `report.md` into the PR)
- confirm that:
  - step screenshots exist and are not zero for pass scenarios
  - failures are classified as `soft_fail` (not `hard_fail`) and contain actionable reasons

Optional ergonomic improvements:
- add a Makefile target or a short README snippet that shows how to run the harness

## Acceptance Criteria
1. There is a clear PR checklist section describing when and how to run the harness.
2. The gate is explicitly “manual” and “opt-in”; it does not run in CI by default.

## Out of Scope
- Enforcing the harness as a CI blocker (explicitly not required).

