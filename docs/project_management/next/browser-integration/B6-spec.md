# B6 – Control Channel Hooks (Pause/Resume) Spec

## Scope
- Make `/ctrl` “Pause Agent” / “Resume” have observable effect on runtime behavior (initial target: `web_eval_agent` execution).
- Expose control state in a way production code can query (e.g., via `StreamingRuntime`), without leaking secrets.
- Ensure pause/resume behavior is deterministic:
  - When paused, tool execution blocks before taking the next browser action/step.
  - When resumed, execution continues.
- Keep auth/rate-limiting behavior intact (only authorized sockets can send control events).

## Acceptance Criteria
1. When a client holds control and sends `pause_agent`, the next `web_eval_agent` step blocks until `resume_agent` is received.
2. Control lock semantics remain enforced (only holder can pause/resume; releasing control unpauses).
3. Tests cover control state transitions and pause gating without requiring a live Socket.IO server (unit-test the state machine + a small “pause gate” helper).
4. Docs include a minimal “how to verify” snippet (manual repro steps) and do not require proprietary tooling.

## Out of Scope
- Building a fully featured browser-use Agent runner with step-by-step streaming and cancellation.
- Multi-user collaboration features beyond existing lock + rate limiting.
