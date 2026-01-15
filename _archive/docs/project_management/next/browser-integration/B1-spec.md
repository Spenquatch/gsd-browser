# B1 – Streaming Core Spec

## Scope
- Port CDP screencast pipeline from `web-agent` into `gsd-browser`:
  - Env toggles `STREAMING_MODE` (`cdp`\|`screenshot`) and `STREAMING_QUALITY` (`low`/`med`/`high`).
  - Start/stop CDP screencast via Playwright, queue frames, attach metadata (timestamp, seq, session id).
  - Forward sampled frames to `ScreenshotManager` (store every Nth frame) and emit stats.
  - Provide `/healthz` JSON with frame latency, drop counts, sampler totals, last frame timestamps.
- Maintain screenshot fallback: when `STREAMING_MODE=screenshot`, emit legacy `browser_update` payloads and bypass CDP namespace.
- Integrate structured logging + metrics (Gauge/counter placeholders) into `gsd-browser` logging utils.

## Acceptance Criteria
1. Template CLI accepts env toggles, streams frames via Socket.IO namespace `/stream` in CDP mode, and falls back to screenshot updates otherwise.
2. `/healthz` endpoint returns JSON with `streaming_mode`, `frame_latency_ms`, `frames_dropped`, `last_frame_ts`, `sampler_totals`, and HTTP 200 when streaming.
3. Screenshot manager stores `agent_step` captures + sampled CDP frames with filtering options identical to `web-agent`.
4. Structured logs (pino/Rich) include frame seq + latency info at `INFO`/`DEBUG` levels.
5. Unit test(s) cover env helper defaults + screenshot sampler limits.

## Out of Scope
- Dashboard UI rendering / HUD overlays (B2 covers UI).
- MCP tool wiring, CLI prompts, or log dashboard auth.
- Browser-use orchestration, install scripts, or telemetry CLI.
