# Browser Integration Feature Plan

## Purpose
Land the WebEval Agent browser-streaming/dashboard stack inside `gsd-browser`. This work ports CDP streaming, dashboard takeover security, MCP screenshot tooling, and the upgraded `browser-use` automation stack into the server without regressing privacy or install ergonomics.

## Guardrails
- **Triads only:** every slice ships as code / test / integration. No mixed commits.
- **Code role:** production Python/TypeScript/server assets only (no tests). Required commands from the worktree: `uv run ruff format --check`, `uv run ruff check`, and any targeted sanity scripts explicitly listed in the spec. Optional manual smoke runs allowed.
- **Test role:** tests/fixtures/harness scripts only. Required commands: `uv run ruff format --check`, and the targeted `uv run pytest <suite>`/`npm run test -- <pattern>` they author.
- **Integration role:** reconciles code+tests, guarantees behavior matches the spec, and must run `uv run ruff format --check`, `uv run ruff check`, `uv run pytest`, `make smoke`, and any spec-specific smoke (e.g., dashboard latency script). They own the final green state.
- **Docs/tasks/session_log edits live only on the orchestration branch** (`feat/browser-integration`). Never edit them from worktrees.
- **Protected assets:** do not mutate `.git`, `gsd-browser/.venv`, sockets under `/tmp`, or dashboard credential stores outside the repo (e.g., OS keychains). Install scripts may write to `~/.local/bin` only when explicitly scoped.

## Branch & Worktree Conventions
- Orchestration branch: `feat/browser-integration`.
- Task branches: `bi-<triad>-<scope>-<role>` (example: `bi-b1-streaming-code`).
- Worktrees: `wt/<branch>` (example: `wt/bi-b1-streaming-code`).

## Triad Overview
1. **B1 – Streaming Core**: Port CDP streaming + screenshot fallback + screenshot manager & health instrumentation into `gsd-browser` (Python service + CLI toggles).
2. **B2 – Dashboard Control & Security**: Bring over the dashboard UI/Socket.IO control channel, auth (API key, nonce, rate limiter), HUD, telemetry scripts, and takeover UX.
3. **B3 – MCP Tooling & Screenshot Services**: Wire MCP tools (`web_eval_agent`, `setup_browser_state`, `get_screenshots`), log plumbing, and diagnostics/smoke scripts that rely on screenshot sampling.
4. **B4 – browser-use Upgrade & OSS LLM Path**: Upgrade to the latest `browser-use` (≥0.11.x), expose configuration for ChatBrowserUse/Ollama/local OSS models, and document the dual stack.
5. **B5 – CDP Streaming Wiring & Metrics**: Wire `CdpScreencastStreamer` to a real Playwright session so CDP mode emits frames end-to-end; align `/healthz` sampler totals with the dashboard HUD.
6. **B6 – Control Hooks (Pause/Resume)**: Make `/ctrl` Pause/Resume affect runtime behavior (initial target: `web_eval_agent`) with holder-only semantics, without requiring a new full agent runner.

Each triad has its own spec (`B*-spec.md`) and code/test/integration kickoff prompts.

## Start Checklist (all tasks)
1. `git checkout feat/browser-integration && git pull --ff-only`
2. Read this plan, `tasks.json`, `session_log.md`, the triad spec, and your kickoff prompt.
3. Set the task status to `in_progress` in `tasks.json` (on the orchestration branch).
4. Add a START entry to `session_log.md`; commit docs (`docs: start <task-id>`).
5. Create the task branch from `feat/browser-integration`; add the worktree: `git worktree add wt/<branch> <branch>`.
6. Do **not** edit docs/tasks/session log within the worktree.

## End Checklist (code/test)
1. Run required commands (code: `uv run ruff format --check`, `uv run ruff check`; test: same + targeted `uv run pytest ...`/`npm run test ...`). Capture outputs.
2. Inside the worktree, commit task changes (no docs updates).
3. Outside the worktree, ensure the task branch references the worktree commit (fast-forward if needed). Do **not** merge to the orchestration branch.
4. Checkout `feat/browser-integration`; update `tasks.json` status, add END entry to `session_log.md` (commands/results/blockers), generate downstream prompts if missing; commit docs (`docs: finish <task-id>`).
5. Remove the worktree: `git worktree remove wt/<branch>`.

## End Checklist (integration)
1. Merge code/test task branches into the integration worktree; reconcile behavior with the spec.
2. Run `uv run ruff format --check`, `uv run ruff check`, `uv run pytest`, `make smoke`, and any spec-mandated smoke (e.g., `scripts/measure_stream_latency.py`). Capture outputs.
3. Commit integration changes on the integration branch.
4. Fast-forward merge the integration branch into `feat/browser-integration`; update `tasks.json` and `session_log.md` with the END entry; commit docs (`docs: finish <task-id>`).
5. Remove the worktree.
