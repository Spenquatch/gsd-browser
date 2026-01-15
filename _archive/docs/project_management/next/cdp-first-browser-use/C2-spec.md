# C2 – Provider compatibility + prompt wrapper

## Scope
### 1) Provider/model policy for browser-use structured output
Reduce `AgentOutput` validation failures by making provider/model expectations explicit:
- Define a “known-good” default model per provider for browser-use (or explicitly fail fast with guidance).
- If a provider/model combo is known to be flaky for structured output:
  - fail fast with actionable configuration guidance, or
  - enable a configurable fallback path (provider/model override) that the operator can opt into.

The goal is not to support every model; the goal is to be predictable and debuggable.

### 2) Prompt wrapper (browser-use-native)
Add a prompt wrapper that is applied via browser-use’s configuration surfaces (not bespoke prompt construction outside browser-use):
- anchor on the provided base URL; avoid navigating away unless the task explicitly requires it
- stop conditions:
  - login required
  - captcha/bot wall
  - “impossible task” due to site restrictions
- allow 1–2 retries for transient UI issues (timeouts, missed clicks) but do not loop indefinitely
- request a final answer in a predictable, extractable format suitable for MCP (`result` field)

### 3) Optional: structured output for extraction tasks
`browser-use` and some providers are sensitive to structured-output expectations. To keep results stable for “extraction” style tasks:
- optionally support a structured output mode (Pydantic-backed) that validates the final result shape before returning it
- keep the default `result` field text-first; structured mode is explicitly opt-in

## Acceptance Criteria
1. Misconfigured provider/model combos fail fast with actionable error messages (what env var to set, which model(s) are supported).
2. Default configuration yields materially fewer `AgentOutput` validation failures on typical real sites (measured via the real-world harness in ADR-0004).
3. Prompt wrapper is applied via browser-use APIs and is testable (unit test asserts the wrapper text contains required stop conditions).

## Out of Scope
- Screenshot capture improvements (C3).
- CDP screencast streaming (C4).
- Run event capture/ranking (C5).
- Take-control dispatch robustness (C6).
