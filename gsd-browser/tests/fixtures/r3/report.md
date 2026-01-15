# gsd real-world sanity report

- Timestamp (UTC): `2026-01-05T00:00:00Z`
- Output dir: `artifacts/real_world_sanity/20260105-000000`

## example-pass

- URL: https://example.com/pass
- Expected: `pass`
- Tool status: `success`
- Classification: `pass`
- Session: `sess-123`
- Screenshots: `2`
- Error events: `0`
- Response: `example-pass/response.json`
- Events: `example-pass/events.json`
- Screenshots index: `example-pass/screenshots.json`

Highlights:
- summary: got the first sentence
- console: no errors observed

## example-soft-fail

- URL: https://example.com/soft-fail
- Expected: `soft_fail`
- Tool status: `failed`
- Classification: `soft_fail`
- Session: `sess-456`
- Screenshots: `1`
- Error events: `3`
- Response: `example-soft-fail/response.json`
- Events: `example-soft-fail/events.json`
- Screenshots index: `example-soft-fail/screenshots.json`
