# C6 – Take-control target robustness (CDP-first)

## Scope
Strengthen take-control so operator inputs always target the active browser-use page/target.

### 1) Target selection
Ensure CDP input dispatch targets the same focus logic that browser-use uses:
- obtain the active/focused CDP session via browser-use session manager
- avoid dispatching to stale target IDs
- gracefully handle detaches by re-acquiring a focused session (best effort)

### 2) Pause/control policy
Clarify and enforce semantics:
- When an operator takes control, auto-pause the agent (policy configurable; default on).
- While paused, ctrl events are accepted (holder-only rules remain).
- On resume:
  - drain/clear queued input events to prevent accidental replay, or
  - apply only a bounded “recent” window (explicitly specified) if we want to support buffered typing.

### 3) Observability
Record rejected/accepted ctrl input events in run events/security logs with bounds:
- rejected reason (not holder, not paused, rate limited)
- dispatch errors (target detached, invalid payload)

## Acceptance Criteria
1. Ctrl input dispatch uses browser-use focused target/session, not an incidental Playwright page.
2. Taking control reliably pauses the agent, and resuming does not replay stale inputs.
3. Tests validate:
   - holder-only and paused-only gating is preserved
   - target re-acquisition occurs on simulated detaches

## Out of Scope
- Streaming adapter (C4) beyond what is needed for target selection.

