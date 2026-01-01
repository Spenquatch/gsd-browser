# Browser Streaming & Dashboard

## Run the streaming server
```bash
STREAMING_MODE=cdp STREAMING_QUALITY=med gsd-browser serve-browser --host 127.0.0.1 --port 5009
```

- Health check: `curl -sS http://127.0.0.1:5009/healthz`
- Dashboard UI: open `http://127.0.0.1:5009/`

## Security controls
The streaming server can enforce a nonce + HMAC handshake for both `/stream` and `/ctrl`.

Environment variables:
- `STREAMING_AUTH_REQUIRED=1` – enable auth (default: off)
- `STREAMING_API_KEY=...` – shared secret used to sign nonces (required if auth enabled)
- `STREAMING_ALLOWED_ORIGINS=http://127.0.0.1:5009,http://localhost:5009` – optional Origin allowlist (default: `*`)
- `STREAMING_NONCE_TTL_SECONDS=60` – nonce expiration window
- `STREAMING_NONCE_USES=4` – how many connections a nonce can authorize
- `STREAMING_RATE_LIMIT_EVENTS_PER_MINUTE=120` – per-SID event budget on `/ctrl`
- `STREAMING_RATE_LIMIT_CONNECTS_PER_MINUTE=30` – per-SID connect budget

Security logging:
- Unauthorized and rate-limited actions are logged to `security.log` in the current working directory.

## Telemetry: measure CDP latency
```bash
uv run python scripts/measure_stream_latency.py --duration 10 --mode cdp --api-key "$STREAMING_API_KEY"
```

