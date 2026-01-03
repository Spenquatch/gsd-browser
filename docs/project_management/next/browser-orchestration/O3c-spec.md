# O3c – Dashboard input capture wiring + manual verification steps

## Scope
- Update dashboard JS to:
  - Capture pointer events over the canvas/img (click, move, wheel).
  - Capture keyboard events when control is held (keydown/keyup/type) and forward to `/ctrl`.
  - Send events only when the holder is active and paused (client-side guard; server remains source of truth).
- Add a minimal manual verification section documenting:
  - Start an agent run
  - Take control (auto-pauses)
  - Click and type (including Enter)
  - Release control and resume agent

## Acceptance Criteria
1. Dashboard can click/scroll/type into the active session while held+paused.
2. Releasing control stops input routing; resuming continues the agent.
3. Manual verification steps are documented and reproducible.

## Manual verification
1. Start a `web_eval_agent(...)` run against a page with an input (keep it running so the session stays active).
2. Open the dashboard and connect.
3. Click **Take Control** (dashboard should show `control: you` and `Paused: true`).
4. Click inside the stream view to focus it, then:
   - click a target in the page
   - type a short string and press Enter
   - scroll the page with the mouse wheel
5. Click **Resume** and confirm input no longer routes while unpaused.
6. Click **Release** and confirm the agent continues normally.
