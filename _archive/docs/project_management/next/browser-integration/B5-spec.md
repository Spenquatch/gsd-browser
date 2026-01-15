# B5 – CDP Streaming Wiring & Dashboard Metrics Spec

## Scope
- Make CDP mode produce real `frame` events end-to-end by wiring `CdpScreencastStreamer.start/stop` to an actual Playwright `Page` lifecycle (initial target: `web_eval_agent` and `mcp-tool-smoke` flows).
- In screenshot mode, emit legacy `browser_update` payloads to `/stream` and store them via `ScreenshotManager` (use `StreamingRuntime.emit_browser_update`).
- Align dashboard HUD stats with `/healthz` payload (fix sampler totals key mismatch so HUD reflects stored samples).
- Ensure `/healthz` reflects meaningful data in both modes after a run (frames received/emitted, sampler totals, last frame timestamps).

## Acceptance Criteria
1. With `STREAMING_MODE=cdp`, the dashboard receives `frame` events during a real Playwright session and renders the canvas; `/healthz` shows non-null `last_frame_ts` and non-zero `frames_received` after a run.
2. With `STREAMING_MODE=screenshot`, the dashboard receives `browser_update` events during the same run path; `/healthz` reports `streaming_mode=screenshot`.
3. `sampler_totals` in `/healthz` matches what the dashboard expects and increments when CDP sampling stores frames.
4. `scripts/measure_stream_latency.py --mode cdp` reports a non-zero `summary.count` when CDP frames are available.
5. Unit tests can simulate the CDP streamer wiring without launching a real browser (mock CDP session events + verify stats/screenshot storage), and do not introduce flaky Playwright dependencies.

## Out of Scope
- Full “agent” orchestration, long-running task loops, or control-channel semantics (handled in B6).
- New providers beyond those already implemented for browser-use (B4).
