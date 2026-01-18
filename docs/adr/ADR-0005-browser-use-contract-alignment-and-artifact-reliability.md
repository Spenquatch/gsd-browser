# ADR-0005: Browser-use contract alignment + artifact reliability (stop conditions, done action, and failure debuggability)

## Status
Proposed

## Context
Recent real-world sanity runs show that `web_eval_agent` is not reliably debuggable and sometimes fails in ways that look “flaky”:
- We intermittently hit `AgentOutput` validation errors (`action` missing), which abort runs.
- Failure runs frequently produce **zero artifacts** (no step screenshots, no run events), causing the real-world harness to classify them as `hard_fail` even when the failure reason is obvious in logs.
- Expected “soft fail” scenarios (e.g. bot walls) do not produce actionable failure reasons in the persisted bundle.

These issues must be addressed at the root: our integration currently conflicts with browser-use’s core output contract and captures artifacts too late (after the session is already torn down).

## Ground truth (browser-use contracts)
The following are browser-use invariants that our integration must respect:
- **Step output contract:** browser-use validates LLM responses against a Pydantic `AgentOutput` schema; the response must include an `action` list (non-empty) on every step.
- **Completion contract:** completion is represented by emitting a single `done` action (with parameters including `text` and `success`). The `done` action’s `text` becomes the agent’s final result (`history.final_result()`).
- **Prompt extension contract:** integrations should add guidance via `extend_system_message` (appending to the default system prompt) rather than instructing the model to emit a different schema that conflicts with `AgentOutput`.
- **Lifecycle/callback contract:** browser-use exposes step hooks and done callbacks that run while the browser session is still alive; session teardown happens after these hooks in the `Agent.run()` cleanup path. Integrations should use these hooks to capture “last known good” artifacts before teardown.

## Problem statement (what’s actually broken)
1. **Prompt wrapper schema conflict**
   - Our current wrapper instructs the model: “When you STOP (or finish), respond with a single-line JSON object only: `{result,status,notes}`”.
   - This instruction conflicts with browser-use’s step contract (“always produce `AgentOutput` with `action`”), causing the model to sometimes omit `action`, leading to validation errors and aborted runs.

2. **Artifact capture happens after teardown on early failures**
   - Our “guarantee screenshots” logic relies on querying the “current page” after `agent.run()` completes.
   - On some failures (including `AgentOutput` validation failures), browser-use may have already stopped/reset the session before we attempt the guarantee capture, resulting in 0 screenshots.

3. **Actionable error signal is not persisted**
   - The harness stores `events.json` filtered to `has_error=true`, but the most important early failures (LLM/provider/validation errors) are not recorded into the run-event store as error events.
   - The harness’s actionable-reason predicate only considers judge failure reasons and network/console error events, not the common “agent output schema validation” failure surfaced in tool payload warnings/errors.

## Decision
We will realign the gsd-browser integration around browser-use’s true contracts:

1. **Stop conditions expressed via `done` action (not a custom JSON schema)**
   - Do not instruct the model to output `{result,status,notes}` at any time during the action loop.
   - Instead, extend the system prompt to:
     - anchor to the base URL
     - define stop conditions (login required, bot wall/captcha, impossible task)
     - instruct that when a stop condition is met, the agent must emit a single `done` action with `success=false` and a concise explanation + recommended remediation
     - when successful, emit `done(success=true)` with the user-facing answer in `text`

2. **Artifact capture must happen before teardown**
   - Capture a final step screenshot and relevant error context inside a browser-use hook that runs before session teardown:
     - step end hook (`on_step_end`) and/or a done callback (`register_done_callback`)
   - Keep “after-run” guarantee capture as a best-effort fallback only (never the primary guarantee).

3. **Persist LLM/provider/validation failures as first-class error events**
   - Any failure that prevents the agent from producing valid `AgentOutput` (or prevents actions from running) must be recorded as a run event with `event_type="agent"` and `has_error=true`.
   - These events must appear in `events.json` and be eligible for ranking in `errors_top`.

4. **Harness classification must treat these failures as actionable**
   - A failure run that includes:
     - step screenshots and/or run events, and
     - a clear tool payload “agent/validation/provider” failure summary
     should classify as `soft_fail` (not `hard_fail`).

## Consequences
### Positive
- Eliminates a major source of “flakiness” by removing a schema-conflicting instruction.
- Makes failures debuggable: even early aborts produce a screenshot + error events.
- Restores the intended semantics of the real-world harness (`hard_fail` becomes a meaningful regression signal).

### Tradeoffs / Risks
- Requires careful prompt wording: stop guidance must be “done-action shaped” and must not contradict browser-use’s action JSON output.
- Requires lifecycle correctness: hooks must run reliably even under failure/timeout paths.
- Some sites will still block automation; the goal is not “always succeed”, but “fail with artifacts and actionable reasons”.

## Implementation plan (triad tryouts)
Create a new tryout series focused on contract alignment + reliability:

1. **A1 – Prompt wrapper contract alignment**
   - Replace the “custom JSON response” instruction with “use `done` action” guidance.
   - Keep base URL anchoring and stop conditions.
   - Add deterministic unit tests asserting:
     - prompt wrapper does not instruct alternate schemas
     - prompt wrapper explicitly instructs `done(success=...)` behavior

2. **A2 – Pre-teardown artifact guarantees**
   - Capture final screenshot within pre-teardown hooks (step end / done callback).
   - Add tests that simulate an early failure path and assert:
     - at least one `agent_step` screenshot is recorded

3. **A3 – Error event persistence**
   - Record validation/provider errors into `RunEventStore` as `has_error=true`.
   - Add deterministic tests asserting these failures show up via `get_run_events(..., has_error=true)`.

4. **A4 – Harness actionable classification**
   - Update harness “actionable reason” predicate to treat these agent/provider/schema failures as actionable when artifacts exist.
   - Add fixture-based tests covering classification outcomes across success / validation failure / provider failure / no-artifact failure.

## Validation / quality gate
Manual, opt-in (not CI):
- Run: `SANITY_REAL_CONFIRM=1 make py-sanity-real`
- Expected outcomes:
  - No `AgentOutput action Field required` failures attributable to prompt conflicts.
  - Expected-pass scenarios produce non-zero step screenshots.
  - Expected-soft-fail scenarios produce artifacts + actionable reasons and classify as `soft_fail` (not `hard_fail`).
