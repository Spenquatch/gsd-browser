# B2 – Dashboard Control & Security Spec

## Scope
- Port dashboard HTML/CSS/JS (canvas renderer, HUD, buttons) into the template’s static assets.
- Implement Socket.IO namespaces `/stream` and `/ctrl`:
  - Control API with `Take Control`, `Release`, `Pause Agent`, `Resume` buttons.
  - Control lock state broadcast, holder SID, timestamps.
- Security:
  - `STREAMING_AUTH_REQUIRED` flag gating API key checks.
  - `STREAMING_API_KEY`, allowed origins, rate limiter per SID, nonce issuance/validation (HMAC with API key).
  - Reject unauthenticated control/stream connections; log to `security.log`.
- Dashboard HUD updates: latency/FPS counters, screenshot sample indicator, error toasts.
- Provide telemetry script `scripts/measure_stream_latency.py` (ported) to test CDP latency with API key support.

## Acceptance Criteria
1. Dashboard loads from template server, renders canvas at ≥30 FPS when CDP enabled, and falls back to `<img>` otherwise.
2. Control buttons lock/pause/resume agent with enforced API key + nonce handshake; unauthorized events are dropped with log entry.
3. Rate limiting and allowed origin list enforced for control namespace.
4. Telemetry script runs via `uv run python scripts/measure_stream_latency.py --duration 10 --mode cdp --api-key ...` and reports p95 latency.
5. Security/streaming runbook updated in docs.

## Out of Scope
- MCP level commands or screenshot tool behaviors (handled in B3).
- Browser-use upgrade or model selection (B4).
