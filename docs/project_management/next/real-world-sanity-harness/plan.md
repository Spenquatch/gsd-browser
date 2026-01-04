# Real-world Sanity Harness + Quality Gates Feature Plan

## Purpose
Add (and standardize) an opt-in real-world scenario harness for `web_eval_agent` that produces PR-reviewable artifacts:
- tool response JSON
- step screenshots (and optionally streaming samples)
- run events (errors-first excerpts)
- a Markdown report + summary JSON bundle

This feature pack is the implementation plan for `docs/adr/ADR-0004-real-world-sanity-harness-and-quality-gates.md`.

## Guardrails
- **Triads only:** every slice ships as code / test / integration. No mixed commits.
- **Code role:** production Python only (no tests). Required commands from the worktree: `uv run ruff format --check`, `uv run ruff check`.
- **Test role:** tests/fixtures only. Required: `uv run ruff format --check` and targeted `uv run pytest ...`.
- **Integration role:** reconciles code+tests to the spec and must run: `uv run ruff format --check`, `uv run ruff check`, `uv run pytest`, `make smoke`.
- **Opt-in:** harness must not run in default CI (`pytest`/`make smoke`) because it depends on external websites and credentials.
- **Privacy:** do not write secrets to disk; keep captured events bounded and avoid bodies.

## Branch & Worktree Conventions
- Orchestration branch: `feat/real-world-sanity-harness`.
- Task branches: `rw-<triad>-<scope>-<role>` (example: `rw-r1-harness-code`).
- Worktrees: `wt/<branch>` (example: `wt/rw-r1-harness-code`).

## References
- `docs/adr/ADR-0004-real-world-sanity-harness-and-quality-gates.md`
- `docs/adr/ADR-0003-cdp-first-browser-use-integration.md` (artifact expectations)
- Existing harness implementation (if present):
  - `gsd-browser/src/gsd_browser/real_world_sanity.py`
  - `gsd-browser/scripts/real_world_sanity.py`

## Output Contract (bundle tree)
Each harness run writes a single directory suitable to attach to a PR:
- `<out>/report.md`
- `<out>/summary.json`
- `<out>/<scenario_id>/response.json`
- `<out>/<scenario_id>/events.json`
- `<out>/<scenario_id>/screenshots/step-<n>-<id>.<ext>`
- `<out>/<scenario_id>/screenshots.json` (index)

## Scenario Set (initial)
All scenarios are “real sites” and must have minimal assertions:
1. `wikipedia-openai-first-sentence` (expected pass)
2. `hackernews-top-story` (expected pass)
3. `github-cdp-heading` (expected pass)
4. `huggingface-papers-botwall-probe` (expected soft_fail)

## Pass/Fail Classification
- `pass`: tool returned `status=success` and `result` is non-empty.
- `soft_fail`: tool returned `partial|failed` but produced artifacts and an actionable failure reason.
- `hard_fail`: tool failed without artifacts or without actionable reasons (signals a tooling regression).

## Triad Overview
1. **R1 – Harness runner + scenario registry**
   - CLI/script shape, scenario selection, output tree, concurrency guardrails.
2. **R2 – Artifact harvesting + classification**
   - Pull screenshots + run events out-of-band; implement stable classification rules.
3. **R3 – Report formatting**
   - Produce a human-readable, PR-friendly Markdown report + summary JSON schema.
4. **R4 – Quality gates**
   - Document a PR checklist gate for changes touching orchestration/streaming; optionally add a Makefile helper target.

## Start Checklist (all tasks)
1. `git checkout feat/real-world-sanity-harness && git pull --ff-only`
2. Read this plan, `tasks.json`, `session_log.md`, the triad spec, and your kickoff prompt.
3. Set the task status to `in_progress` in `tasks.json` (on the orchestration branch).
4. Add a START entry to `session_log.md`; commit docs (`docs: start <task-id>`).
5. Create the task branch from `feat/real-world-sanity-harness`; add the worktree: `git worktree add wt/<branch> <branch>`.
6. Do **not** edit docs/tasks/session log within the worktree.

## End Checklist (code/test)
1. Run required commands (code: `uv run ruff format --check`, `uv run ruff check`; test: same + targeted `uv run pytest ...`). Capture outputs.
2. Inside the worktree, commit task changes (no docs updates).
3. Checkout `feat/real-world-sanity-harness`; update `tasks.json` status and add END entry to `session_log.md`; commit docs (`docs: finish <task-id>`).
4. Remove the worktree: `git worktree remove wt/<branch>`.

## End Checklist (integration)
1. Merge code/test branches into the integration worktree; reconcile behavior with the spec.
2. Run `uv run ruff format --check`, `uv run ruff check`, `uv run pytest`, `make smoke`. Capture outputs.
3. Commit integration changes on the integration branch.
4. Fast-forward merge the integration branch into `feat/real-world-sanity-harness`; update `tasks.json` and `session_log.md` with the END entry; commit docs (`docs: finish <task-id>`).
5. Remove the worktree.

