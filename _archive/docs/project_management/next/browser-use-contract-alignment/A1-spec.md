# A1 — Prompt wrapper contract alignment

## Scope
Fix the system-prompt extension so it does not conflict with browser-use’s `AgentOutput` schema.

### Requirements
- Keep: base URL anchoring and “do not leave the site unless required”.
- Keep: stop conditions (login required, captcha/bot wall, impossible task).
- Replace: any instruction that asks the model to output a custom JSON schema outside the browser-use action loop.
- Explicitly instruct: represent completion and stopping only via a single `done` action:
  - `done(success=true, text=<answer>)` on success
  - `done(success=false, text=<why + remediation>)` on stop conditions / failures

## Acceptance criteria
1. Unit tests assert the prompt wrapper:
   - does not instruct alternate “result/status JSON only” outputs
   - does instruct `done(success=...)` semantics
2. No new prompt wrapper guidance contradicts browser-use “action list should never be empty”.

## Out of scope
- Screenshot capture changes (A2).
- Run event capture/persistence changes (A3).
- Harness classification changes (A4).
