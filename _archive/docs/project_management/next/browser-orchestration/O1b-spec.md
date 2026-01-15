# O1b – Step callbacks + screenshot artifacts + pause gating

## Scope
- Add step-level integration to `web_eval_agent`:
  - Use browser-use step hooks (`register_new_step_callback` and/or `on_step_end`) to record `agent_step` screenshots in `ScreenshotManager`.
  - Wire pause gating so that between steps the agent blocks while paused (controlled by `/ctrl` state).
- Ensure response remains compact: return references only; screenshots stay in storage and are retrieved via `get_screenshots`.

## Acceptance Criteria
1. When paused, agent progress stops between steps until resumed.
2. At least one `agent_step` screenshot is recorded per run and retrievable via `get_screenshots(session_id=...)`.
3. The JSON response includes updated `artifacts` counts (e.g., screenshot counts) and retrieval hints in `next_actions`.
4. No inline images are returned by default; stdout remains clean.
5. Tests cover pause gating behavior and screenshot-recording calls (with mocks/stubs).

## Out of Scope
- Run event store / `get_run_events` (O2*).
- Take-control input routing (O3*).

