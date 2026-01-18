# ADR-0001: Agent orchestration and “return answer” contract

## Status
Proposed

## Context
We want any MCP-capable LLM client (Codex, Claude Code, etc.) to be able to delegate tasks to `gsd-browser` and receive back a useful, human-readable answer.

Today, `gsd-browser` exposes MCP tools (`web_eval_agent`, `setup_browser_state`, `get_screenshots`) but `web_eval_agent` is effectively a **screenshot-only stub**:
- It navigates to a URL with Playwright, captures a single screenshot, and returns a `session_id`.
- It does not use the `task` argument to drive automation or extraction.
- Users often end up manually parsing screenshots outside the MCP flow.

Upstream reference implementation (`Operative-Sh/web-eval-agent`, cloned locally to `/tmp/refresh-web-eval-agent` for inspection) demonstrates the intended architecture:
- `webEvalAgent/mcp_server.py` dispatches `web_eval_agent` to `webEvalAgent/src/tool_handlers.py:handle_web_evaluation`.
- `handle_web_evaluation` builds a prompt (`webEvalAgent/src/prompts.py`) and runs a browser-use Agent loop (`webEvalAgent/src/browser_utils.py:run_browser_task`).
- It formats a rich report (console/network/timeline + conclusion) and returns it to the MCP client.

Our local `~/web-agent` adds critical improvements that match our product intent:
- Explicit extraction and display of the agent’s **final answer** (see `~/web-agent/ISSUES_AND_FIXES.md` “Issue #7” and `~/web-agent/webEvalAgent/src/browser_utils.py` + `tool_handlers.py`).
- Robust, low-latency CDP streaming + pause/take-control UX; and reducing context pollution by separating large artifacts from the tool text response.

Constraints we must preserve:
- MCP stdio servers must not write non-JSON-RPC content to stdout during operation (Codex/other clients will fail the handshake).
- Screenshot/video artifacts must not be dumped into the main tool text response by default (token and privacy concerns).
- `gsd-browser` uses newer `browser-use` (B4), so the upstream orchestration concepts must be adapted for API changes.

## Decision
Implement a real `web_eval_agent` orchestration flow in `gsd-browser` that:
1. Runs a browser automation agent loop (browser-use) to execute the provided `task` against the target `url`.
2. Returns a **text-first response** that includes an explicit “final answer” and a concise report summary.
3. Stores large artifacts (screenshots, sampled frames, console/network logs) out-of-band and returns references (`session_id`, counts, timestamps) plus retrieval guidance.

### MCP response contract (proposed)
`web_eval_agent(url, task, headless_browser=...)` returns a single `TextContent` containing:
- `Result:` (the final extracted answer, when available)
- `Summary:` short bullets (success/failure, notable UX issues, etc.)
- `Artifacts:` `session_id`, counts (screenshots stored, stream samples stored), and next actions:
  - “Use `get_screenshots(session_id=..., screenshot_type='agent_step')`”
  - (future) “Use `get_run_events(session_id=...)`” for console/network/timeline

`get_screenshots(...)` remains the on-demand path for images (opt-in).

### How the “final answer” is extracted
Adopt the `~/web-agent` intent:
- The agent run yields an “agent history/result” object.
- Prefer an explicit accessor (e.g., `final_result()` or the equivalent in the newer browser-use API).
- Fall back to a best-effort extraction strategy only if the explicit API is missing.

In `browser-use>=0.11`, `Agent.run()` returns an `AgentHistoryList` that exposes:
- `final_result()` (string/None)
- `structured_output` / `get_structured_output(model)` when `output_model_schema` is provided

## Consequences
Positive:
- The core user expectation (“ask a question, get an answer”) is met directly in the MCP tool response.
- Artifacts are still available (screenshots, streaming, logs) without forcing them into the context window.
- Clear separation between operator UI (dashboard) and MCP payloads.

Tradeoffs / risks:
- `browser-use` version differences require careful API adaptation and new tests around “final answer extraction”.
- Returning “rich reports” must remain bounded to avoid token blowups; truncation + “see dashboard / fetch artifacts” becomes the norm.
- We must explicitly define what the tool guarantees (answer vs. best-effort) to avoid “silent partial” behaviors.

## Implementation Notes (non-code)
Recommended call flow (conceptual):
1. Create `session_id` + `tool_call_id` at tool entry.
2. Ensure dashboard/streaming runtime is available.
3. Create/attach a Playwright browser context suitable for:
   - browser-use Agent control
   - CDP streaming (optional)
   - persisted auth state reuse (`setup_browser_state`)
4. Run agent loop with a step callback that:
   - respects pause (`/ctrl` pause gate) between steps
   - records `agent_step` screenshots to `ScreenshotManager`
   - optionally emits streaming updates (CDP/screenshot mode)
5. On completion:
   - extract “final answer”
   - produce bounded text summary
   - return `session_id` + artifact counts and retrieval instructions

Testing requirements (conceptual):
- Unit tests for “final answer extraction” behavior with mocked agent result objects.
- Integration tests to ensure `web_eval_agent` returns a `Result:` line when extraction is available.
- Regression tests to ensure `web_eval_agent` does not include image payloads in the default response.

## Open Questions
1. Do we want to support an explicit structured output mode (Pydantic schema) for extraction tasks?
2. Should the tool expose multiple response modes (`compact` vs `dev`) as an argument, or as a config default?
3. Should the tool return “answer only” for certain task types, or always return a structured report object (with `result` + `summary`)?

## References
- Upstream architecture (sunset; GitHub): `Operative-Sh/web-eval-agent`
- Upstream clone (local inspection): `/tmp/refresh-web-eval-agent/webEvalAgent/mcp_server.py`, `/tmp/refresh-web-eval-agent/webEvalAgent/src/tool_handlers.py`, `/tmp/refresh-web-eval-agent/webEvalAgent/src/browser_utils.py`
- Local enhancements: `~/web-agent/ISSUES_AND_FIXES.md`, `~/web-agent/webEvalAgent/src/browser_utils.py`, `~/web-agent/webEvalAgent/src/tool_handlers.py`
- Current stub: `gsd-browser/src/gsd_browser/mcp_server.py`
- Current artifact channel: `gsd-browser/src/gsd_browser/screenshot_manager.py`, `gsd-browser/src/gsd_browser/streaming/*`
- browser-use API references: `browser-use/browser-use` (DeepWiki: AgentHistoryList in `browser_use/agent/views.py`; callbacks in `browser_use/agent/service.py`)
