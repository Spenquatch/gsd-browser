# C3 – Step screenshots guarantee (CDP-first fallback)

## Scope
Guarantee a minimum level of screenshot coverage for `web_eval_agent` runs, even when browser-use does not populate `BrowserStateSummary.screenshot`.

### 1) Capture strategy (primary + fallback)
In the step callback (`register_new_step_callback(...)` or equivalent):
- Primary: use `BrowserStateSummary.screenshot` / `screenshot_base64` when present.
- Fallback: capture from the “current page” via browser-use actor APIs:
  - `page = await browser_session.get_current_page()`
  - `await page.screenshot(format="jpeg", quality=80)` (or equivalent)

### 2) Bounds + guarantees
- Always record at least:
  - step 1 screenshot (first observation)
  - last step screenshot (on done/failure)
- Enforce a strict per-session cap (default: keep last 50 `agent_step` screenshots).

### 3) Metadata
Each recorded `agent_step` screenshot must include:
- `session_id`, `captured_at`, `step`
- url + title (best effort)
- `has_error` boolean
- `source`: `"browser_state_summary"` | `"current_page_fallback"`
- optional flags derived from browser-use history/judgement (only if judge mode is enabled and the fields are present)

## Acceptance Criteria
1. Real-world harness runs produce `agent_step` screenshots consistently (non-zero for typical scenarios).
2. If `BrowserStateSummary` has no screenshot, fallback capture records an image without crashing the run.
3. Screenshots are bounded and oldest are evicted beyond the cap.
4. Unit tests validate:
   - fallback is attempted when summary screenshot missing
   - cap/eviction behavior

## Out of Scope
- Streaming frames (C4).
- Run events capture/ranking (C5).
- Take-control dispatch robustness (C6).
