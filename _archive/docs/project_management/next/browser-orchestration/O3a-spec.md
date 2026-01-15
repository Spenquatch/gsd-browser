# O3a – Take-control server API + holder/paused gating

## Scope
- Add new `/ctrl` socket events for browser inputs:
  - `input_click`, `input_move`, `input_wheel`, `input_keydown`, `input_keyup`, `input_type`
- Enforce policy:
  - Only the holder SID can send input events.
  - Inputs are accepted only while **paused**.
  - Rate limiting and security logging for rejected events.
- No CDP dispatch yet; events may be accepted and queued/dropped with clear logs.

## Acceptance Criteria
1. Non-holder inputs are rejected and logged.
2. Holder inputs are rejected unless paused (paused-only policy).
3. Rate limits apply to input events and are logged when exceeded.
4. Unit tests validate gating/validation without requiring a real browser.

## Out of Scope
- Actual CDP input dispatch (O3b).
- Dashboard JS input capture (O3c).

