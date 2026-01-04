# ADR-0004: Real-world sanity harness + quality gates (reports + screenshots)

## Status
Proposed

## Context
Unit tests can validate contracts (JSON shape, bounds, gating rules), but they cannot ensure the tool “feels like a browser agent” in real usage.
We need a repeatable way to run representative real-world tasks that:
- exercise navigation + interaction + extraction
- surface friction (bot walls, timing, selector misses, broken flows)
- generate artifacts (step screenshots + event excerpts) to diagnose and iterate
- produce human-readable reports suitable for PR review.

The `~/web-eval-agent` repo implicitly used real apps (local dev) and had a “rich report” in the tool response itself.
`gsd-browser` intentionally keeps MCP responses compact; therefore the harness must also pull artifacts out-of-band.

## Decision
Add an opt-in “real-world sanity harness” to `gsd-browser` that:
- runs a curated set of realistic scenarios through `web_eval_agent`
- collects:
  - the tool JSON response
  - step screenshots (`agent_step`) and (optionally) streaming samples
  - run event excerpts (errors-first)
- writes:
  - a JSON bundle
  - a Markdown report with links to the saved screenshots
  - a directory tree suitable to attach to a PR or share internally.

This harness is intentionally **not** part of default `pytest` or `make smoke` because it depends on:
- external websites
- model/provider credentials
- internet variability.

## Consequences
### Positive
- We get fast feedback on “does this work on real sites?” with artifacts.
- We can standardize regression scenarios (“this used to work; now it’s broken”).
- We can quickly identify which failures are product issues vs site defenses.

### Tradeoffs / Risks
- Real sites change; assertions must be minimal and results will vary over time.
- Running against third-party sites has ethical/security considerations (rate limits, ToS).
- A harness that is too strict will be flaky; too loose will hide regressions.

## Implementation Notes

### 1) Harness shape
Add a script (or subcommand) that:
- accepts `--out <dir>` and writes one run directory per execution:
  - `runs/<timestamp>/<scenario_id>/response.json`
  - `runs/<timestamp>/<scenario_id>/events.json`
  - `runs/<timestamp>/<scenario_id>/screenshots/step-<n>.jpg|png`
  - `runs/<timestamp>/report.md`
  - `runs/<timestamp>/summary.json`
- supports selecting scenarios by id and limiting concurrency to avoid overloading sites.

### 2) Scenario set (initial)
Each scenario must be “real” (no `example.com`), and designed to surface real friction.
Initial recommended scenarios:
1. **Wikipedia (content extraction):**
   - URL: `https://en.wikipedia.org/wiki/OpenAI`
   - Task: “Find the first paragraph and return the first sentence. Include the final URL.”
   - Expected: success; no auth; stable.
2. **Hacker News (navigation + extraction):**
   - URL: `https://news.ycombinator.com/`
   - Task: “Return the title + link of the first story.”
   - Expected: success; minimal JS; stable.
3. **GitHub repo navigation (UI interaction):**
   - URL: `https://github.com/browser-use/browser-use`
   - Task: “Open the README and find the section that mentions CDP; return the heading and the anchor URL.”
   - Expected: may require some JS but generally stable; good for scroll/find.
4. **Bot-wall friction probe (expected partial/fail):**
   - URL: `https://huggingface.co/papers`
   - Task: “Identify the top paper and open it; return title + URL. If blocked, report what blocked you and which remediation to try.”
   - Expected: may trigger WAF/anti-bot; should produce useful failure reasons + screenshots.

### 3) Output expectations and pass/fail classification
The harness should classify a scenario as:
- `pass`: tool returned `status=success` and `result` is non-empty.
- `soft_fail`: tool returned `partial` or `failed` but produced artifacts and an actionable failure reason.
- `hard_fail`: tool failed without artifacts or without actionable reasons (this indicates a tooling regression).

### 4) Quality gates for PRs
Add a “manual checklist” gate for PRs that touch orchestration/streaming:
- run the harness locally
- attach the generated report directory (or paste the Markdown summary)
- confirm screenshots exist for each step and failure modes are understandable.

### 5) Deterministic tests remain separate
Continue to enforce deterministic CI gates with:
- contract tests (O1a)
- pause + screenshot recording behavior tests (O1b)
- run event store filtering/limits tests (O2a/O2b)
- control gating and mapping tests (O3a/O3b)

The harness should be used to drive iteration, not to block CI by default.

## Open Questions
1. Do we want a small set of “blessed” scenarios that must be run before merging into `main`?
2. Should we add provider-specific scenario sets (e.g., one tuned for `chatbrowseruse`)?
3. Where should artifacts be stored by default (repo-local `artifacts/` vs `~/.config/gsd-browser/`), and should we auto-prune?

## References
- `docs/adr/ADR-0001-agent-orchestration-and-answer-contract.md`
- `docs/adr/ADR-0002-operator-dashboard-streaming-and-take-control.md`
- `~/web-eval-agent/webEvalAgent/src/tool_handlers.py` (report formatting patterns; errors-first + timeline + truncation)
- DeepWiki review of `browser-use/browser-use` Agent hooks and history error/judgement APIs

