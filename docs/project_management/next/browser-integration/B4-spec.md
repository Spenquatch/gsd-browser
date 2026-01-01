# B4 – browser-use Upgrade & OSS Model Support Spec

## Scope
- Upgrade template dependencies to `browser-use>=0.11.0` (latest available), adjusting imports/config per upstream breaking changes.
- Surface configuration for: ChatBrowserUse (cloud API), OpenAI/Gemini fallback, and local OSS/Ollama models (documented env vars, CLI flags).
- Provide config validation ensuring incompatible combos error early (e.g., missing API key when cloud mode selected).
- Update docs to explain the dual stack (cloud vs local) and when to choose each.
- Add smoke tests verifying the orchestrator instantiates `browser-use` with both a mocked cloud provider and a local provider stub.

## Acceptance Criteria
1. `pyproject.toml` pins `browser-use` to the new version; `poetry lock`/uv sync updated.
2. Template CLI accepts `--llm-provider` / env toggles for `chatbrowseruse`, `openai`, `ollama`, etc., with validation + helpful errors.
3. README/docs describe how to enable the OSS path (Ollama/local) and ChatBrowserUse, including env vars and install steps.
4. Smoke tests (pytest) cover instantiating both provider types with stubbed secrets.
5. Integration verifies `poetry export`/`uv sync` succeed without regressions.

## Out of Scope
- Streaming pipeline, dashboard UI/security (B1/B2).
- MCP screenshot tool specifics (B3).
