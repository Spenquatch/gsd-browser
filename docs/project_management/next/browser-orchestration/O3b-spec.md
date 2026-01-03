# O3b – CDP input dispatch implementation (keyboard correctness)

## Scope
- Implement CDP routing for the input events introduced in O3a:
  - Click: mousePressed + mouseReleased
  - Scroll: mouseWheel
  - Keys: `Input.dispatchKeyEvent` for keydown/keyup, with correct modifier mapping.
  - Typing: printable chars via `char` events or repeated key events as appropriate.
- Focus on keyboard correctness:
  - Enter behavior for form submission (sequence that reliably triggers submit).
  - Modifier keys (ctrl/shift/alt/meta) mapping.
  - Avoid sending inputs when no active session is available.
- Prefer using browser-use BrowserSession CDP access to avoid dual CDP stacks.

## Acceptance Criteria
1. For an active run with control held + paused, inputs affect the active page via CDP.
2. Enter key reliably triggers form submission.
3. Typing yields correct text in focused input.
4. Unit tests validate parameter mapping and dispatch calls (mock CDP client).

## Out of Scope
- Dashboard JS input capture (O3c).

